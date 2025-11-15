"""
ModalFlowRunner: Main orchestrator for filling LinkedIn Easy Apply modal forms.

This module implements the core logic for parsing modals, applying rules,
resolving fields, and controlling the flow between multiple modal steps.
"""

import re
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from playwright.async_api import Page, Locator, expect

from core.selectors import selectors
from modal_flow.profile_schema import CandidateProfile
from modal_flow.rules_store import RuleStore
from modal_flow.normalizer import QuestionNormalizer
from modal_flow.rules_engine import RulesEngine
from modal_flow.learning_config import LearningConfig
from modal_flow.document_upload import (
    CoverLetterLazyGenerator,
    DocumentPaths,
    ModalDocumentUploader,
)


# Regex patterns for navigation buttons
NEXT_BTN_RX = re.compile(r"(next|continue|review|proceed|далее|продолжить|обзор|проверить)", re.I)
SUBMIT_BTN_RX = re.compile(r"(submit|send|finish|отправить|подтвердить|submit application)", re.I)
VALIDATION_ERROR_RX = re.compile(r"(error|invalid|required|неверный|ошибка|обязательное)", re.I)


@dataclass
class FieldInfo:
    """Information about a form field."""
    field_type: str  # radio, checkbox, select, combobox, text, number
    question: str
    options: Optional[List[str]] = None
    element: Optional[Locator] = None
    required: bool = False


@dataclass
class ModalFlowRunResult:
    """Summary of a modal flow execution."""

    completed: bool
    submitted: bool
    validation_errors: List[str]
    steps_processed: int


class ModalFlowRunner:
    """
    Main runner for processing LinkedIn Easy Apply modal forms.
    
    Coordinates ModalParser, RulesEngine, FieldResolvers, and FlowController.
    """
    
    def __init__(
        self,
        page: Page,
        profile: CandidateProfile,
        rule_store: RuleStore,
        normalizer: Optional[QuestionNormalizer] = None,
        llm_delegate: Optional[Any] = None,  # Will be BaseLLMDelegate type
        learning_config: Optional[LearningConfig] = None,
        logger: Optional[logging.Logger] = None,
        capture_screenshots: bool = True,
    ):
        """
        Initialize ModalFlowRunner.
        
        Args:
            page: Playwright Page instance
            profile: Candidate profile for filling forms
            rule_store: RuleStore instance
            normalizer: QuestionNormalizer instance (creates default if None)
            llm_delegate: Optional LLMDelegate for fallback decisions
            learning_config: Optional configuration for automatic learning
            logger: Optional logger instance
        """
        self.page = page
        self.profile = profile
        self.rule_store = rule_store
        self.normalizer = normalizer or QuestionNormalizer()
        self.llm_delegate = llm_delegate
        self.logger = logger or logging.getLogger(__name__)
        self._document_uploader: Optional[ModalDocumentUploader] = None
        self.capture_screenshots = capture_screenshots
        
        # Initialize RulesEngine with learning_config
        self.rules_engine = RulesEngine(
            profile=profile,
            rule_store=rule_store,
            normalizer=self.normalizer,
            llm_delegate=llm_delegate,
            learning_config=learning_config,
            logger=self.logger
        )
    
    async def run(
        self,
        max_steps: int = 8,
        should_submit: bool = True,
        job_context: Optional[Dict[str, Any]] = None,
        document_paths: Optional[DocumentPaths] = None,
        lazy_generator: Optional[CoverLetterLazyGenerator] = None,
    ) -> ModalFlowRunResult:
        """
        Main entry point: Process modal forms until completion or max steps.
        
        Args:
            max_steps: Maximum number of modal steps to process
        """
        self.logger.info(
            "Starting modal flow (max_steps=%s, should_submit=%s)",
            max_steps,
            should_submit,
        )
        if job_context:
            self.logger.debug("Modal flow job context: %s", job_context)

        self._document_uploader = None
        if document_paths:
            self._document_uploader = ModalDocumentUploader(
                page=self.page,
                normalizer=self.normalizer,
                document_paths=document_paths,
                logger=self.logger,
                lazy_generator=lazy_generator,
            )
        
        previous_progress_percentage: Optional[int] = None

        for step in range(max_steps):
            self.logger.info(f"[MODAL_FLOW_STEP] Processing step {step + 1}/{max_steps}")
            is_same_dialog = False
            
            # Wait for spinners to disappear
            await self._wait_for_spinners_to_disappear()
            
            # Find active modal
            modal = await self._active_modal()
            if not modal:
                self.logger.info("[MODAL_FLOW_STEP] No active modal found. Ending run.")
                result = ModalFlowRunResult(
                    completed=True,
                    submitted=False,
                    validation_errors=[],
                    steps_processed=step,
                )
                self._document_uploader = None
                return result
            
            # Store reference to current modal for transition detection
            stale_modal_reference = modal
            
            # Try to get modal text for logging
            try:
                modal_text = await modal.inner_text()
                modal_text_preview = modal_text[:200] + "..." if len(modal_text) > 200 else modal_text
                self.logger.info(f"[MODAL_FLOW_STEP] Modal content preview: {modal_text_preview}")
                
                current_progress_percentage = self._extract_progress_percentage_from_text(modal_text)
                if current_progress_percentage is not None:
                    self.logger.info(f"[PROGRESS] Current dialog progress: {current_progress_percentage}%")
                    if previous_progress_percentage is not None:
                        if current_progress_percentage == previous_progress_percentage:
                            is_same_dialog = True
                            self.logger.warning(
                                f"[DIALOG_CHECK] Dialog did not change after Next click (progress still "
                                f"{current_progress_percentage}%). Will skip already filled fields."
                            )
                        else:
                            self.logger.info(
                                f"[DIALOG_CHECK] Dialog changed: "
                                f"{previous_progress_percentage}% -> {current_progress_percentage}%"
                            )
                    previous_progress_percentage = current_progress_percentage
                else:
                    self.logger.debug(
                        "[PROGRESS] Progress percentage not found in modal text; cannot detect dialog change."
                    )
            except Exception as e:
                self.logger.debug(f"[MODAL_FLOW_STEP] Could not get modal text: {e}")
            
            # Fill all fields in current modal
            self.logger.info(f"[MODAL_FLOW_STEP] Filling fields in step {step + 1} (is_same_dialog={is_same_dialog})")
            
            # Capture screenshot before filling
            if self.capture_screenshots:
                try:
                    screenshots_dir = Path("screenshots/modal_flow_debug")
                    screenshots_dir.mkdir(parents=True, exist_ok=True)
                    screenshot_path = screenshots_dir / f"step_{step + 1:02d}_before_fill.png"
                    await self.page.screenshot(path=str(screenshot_path), full_page=True)
                    self.logger.info(f"[SCREENSHOT] Saved: {screenshot_path}")
                except Exception as e:
                    self.logger.debug(f"[SCREENSHOT] Failed to capture screenshot: {e}")
            
            await self._fill_modal(modal, is_same_dialog=is_same_dialog)
            self.logger.info(f"[MODAL_FLOW_STEP] Fields filled in step {step + 1}")
            
            # Capture screenshot after filling
            if self.capture_screenshots:
                try:
                    screenshots_dir = Path("screenshots/modal_flow_debug")
                    screenshots_dir.mkdir(parents=True, exist_ok=True)
                    screenshot_path = screenshots_dir / f"step_{step + 1:02d}_after_fill.png"
                    await self.page.screenshot(path=str(screenshot_path), full_page=True)
                    self.logger.info(f"[SCREENSHOT] Saved: {screenshot_path}")
                except Exception as e:
                    self.logger.debug(f"[SCREENSHOT] Failed to capture screenshot: {e}")
            
            # Check for Submit button first (higher priority)
            # Try multiple ways to find submit button
            submit_btn = None
            submit_btn_text = None
            
            # Method 1: By role with regex
            try:
                submit_btn_candidates = modal.get_by_role("button", name=SUBMIT_BTN_RX)
                submit_count = await submit_btn_candidates.count()
                if submit_count > 0:
                    submit_btn = submit_btn_candidates.first
                    if await submit_btn.is_visible():
                        submit_btn_text = await submit_btn.inner_text()
                        self.logger.info(f"[SUBMIT_CHECK] Submit button found by role: '{submit_btn_text}'")
                    else:
                        submit_btn = None
            except Exception as e:
                self.logger.debug(f"[SUBMIT_CHECK] Could not find submit button by role: {e}")
                submit_btn = None
            
            # Method 2: Try to find by text content if method 1 failed
            if not submit_btn:
                try:
                    # Get all buttons and check their text
                    all_buttons = modal.get_by_role("button")
                    button_count = await all_buttons.count()
                    self.logger.debug(f"[SUBMIT_CHECK] Checking {button_count} buttons for submit button")
                    
                    for i in range(button_count):
                        btn = all_buttons.nth(i)
                        try:
                            if await btn.is_visible():
                                btn_text = await btn.inner_text()
                                btn_text_lower = btn_text.lower().strip()
                                # Check if button text matches submit pattern
                                if SUBMIT_BTN_RX.search(btn_text_lower):
                                    submit_btn = btn
                                    submit_btn_text = btn_text
                                    self.logger.info(f"[SUBMIT_CHECK] Submit button found by text: '{submit_btn_text}'")
                                    break
                        except Exception:
                            # Skip buttons that can't be checked
                            continue
                except Exception as e:
                    self.logger.debug(f"[SUBMIT_CHECK] Could not find submit button by text: {e}")
            
            if submit_btn and submit_btn_text:
                if should_submit:
                    self.logger.info(f"[SUBMIT] Submit button found: '{submit_btn_text}', clicking.")
                    await self._safe_click(submit_btn)
                    self.logger.info("Submit button clicked. Flow finished.")
                    submitted = True
                else:
                    self.logger.info(
                        f"[SUBMIT] Submit button found: '{submit_btn_text}', skipping click due to DRY RUN mode."
                    )
                    submitted = False
                result = ModalFlowRunResult(
                    completed=True,
                    submitted=submitted,
                    validation_errors=[],
                    steps_processed=step + 1,
                )
                self._document_uploader = None
                return result
            else:
                self.logger.debug(f"[SUBMIT_CHECK] Submit button not found in step {step + 1}")
            
            # Look for Next button
            next_btn = modal.get_by_role("button", name=NEXT_BTN_RX).first
            if await next_btn.is_visible():
                self.logger.info("Next button found, clicking.")
                await self._safe_click(next_btn)
                
                # Wait for modal transition
                # LinkedIn updates the modal content, not the modal container itself
                # So we just wait for the content to update
                await self._wait_for_modal_transition(stale_modal_reference)
                
                # Continue to next iteration to process the new modal content
                # DO NOT check for validation errors here - the new content
                # hasn't been processed yet (no fields filled)
            else:
                self.logger.warning("No navigation button found. Ending run.")
                result = ModalFlowRunResult(
                    completed=False,
                    submitted=False,
                    validation_errors=["Navigation button not found"],
                    steps_processed=step + 1,
                )
                self._document_uploader = None
                return result
        
        self.logger.error(
            "Max steps (%s) reached. Aborting to prevent infinite loop.", max_steps
        )
        self._document_uploader = None
        return ModalFlowRunResult(
            completed=False,
            submitted=False,
            validation_errors=["Max steps reached"],
            steps_processed=max_steps,
        )
    
    async def _check_for_validation_errors(self, modal: Locator) -> List[str]:
        """
        Check for visible validation error messages in the modal.
        
        Args:
            modal: The locator for the current modal.
            
        Returns:
            List of validation error messages if found.
        """
        # A simple approach: look for any element with text matching common error keywords.
        # This can be refined to look for specific aria roles like 'alert'.
        error_messages = modal.get_by_text(VALIDATION_ERROR_RX)
        count = await error_messages.count()
        collected_errors: List[str] = []
        
        for i in range(count):
            error = error_messages.nth(i)
            if await error.is_visible():
                error_text = await error.inner_text()
                self.logger.warning(f"Found potential validation error: '{error_text}'")
                collected_errors.append(error_text.strip())
                
                # Try to identify which field has the error
                try:
                    parent = error.locator(selectors["xpath_ancestor_with_class_or_id"])
                    parent_info = await parent.evaluate(
                        """(el) => ({
                            tag: el.tagName,
                            id: el.id,
                            class: el.className,
                            text: el.textContent ? el.textContent.substring(0, 100) : ''
                        })"""
                    )
                    self.logger.warning(f"Error location context: {parent_info}")
                except Exception:
                    pass
        
        return collected_errors

    async def _active_modal(self) -> Optional[Locator]:
        """
        Find the currently active modal dialog.
        
        Returns:
            Locator for the active modal, or None if no modal found
        """
        dialogs = self.page.get_by_role("dialog")
        count = await dialogs.count()
        
        if count == 0:
            return None
        
        # Return the last visible dialog (most likely the active one)
        return dialogs.nth(count - 1)
    
    def _extract_progress_percentage_from_text(self, modal_text: str) -> Optional[int]:
        """
        Extract the progress percentage (e.g., '44%') from modal text.
        
        Args:
            modal_text: Text content of the modal.
        
        Returns:
            Integer percentage (0-100) if found, otherwise None.
        """
        match = re.search(r"(\d{1,3})%", modal_text)
        if not match:
            return None
        try:
            percentage = int(match.group(1))
            if 0 <= percentage <= 100:
                return percentage
        except ValueError:
            pass
        return None
    
    async def _fill_modal(self, modal: Locator, is_same_dialog: bool = False):
        """
        Fill all fields in the current modal.
        
        Args:
            modal: Locator for the modal dialog
            is_same_dialog: Indicates if the dialog content did not change after Next click
        """
        self.logger.info(f"[MODAL_FILL] Starting to fill modal fields (is_same_dialog={is_same_dialog})")
        if is_same_dialog:
            self.logger.warning(
                "[MODAL_FILL] Same dialog detected after navigation. "
                "Skipping fields that are already filled."
            )
        
        # Attach documents if required before filling other fields
        if self._document_uploader:
            self.logger.info("[MODAL_FILL] Handling document upload")
            await self._document_uploader.handle_modal(modal)

        # Process fields in order: radio groups, checkboxes, comboboxes, number inputs, textboxes
        self.logger.info("[MODAL_FILL] Processing radio groups")
        await self._handle_radio_groups(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Processing checkboxes")
        await self._handle_checkboxes(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Processing comboboxes")
        await self._handle_comboboxes(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Processing number inputs")
        await self._handle_number_inputs(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Processing textboxes")
        await self._handle_textboxes(modal, is_same_dialog=is_same_dialog)
        self.logger.info("[MODAL_FILL] Finished filling modal fields")
    
    async def _handle_radio_groups(self, modal: Locator, is_same_dialog: bool = False):
        """Handle radio button groups."""
        # Wait for all radio buttons to be loaded (they might load dynamically)
        # Try to wait for at least one radio button to appear, then wait a bit more
        try:
            await modal.get_by_role("radio").first.wait_for(state="visible", timeout=2000)
            # Give additional time for all radio buttons to load
            await self.page.wait_for_timeout(500)
        except Exception:
            # If no radio buttons found, continue anyway
            pass
        
        radios = modal.get_by_role("radio")
        count = await radios.count()
        
        if count == 0:
            return
        
        # Log all found radio buttons for debugging
        self.logger.debug(f"Found {count} total radio button(s)")
        for i in range(count):
            r = radios.nth(i)
            name_attr = await r.get_attribute("name") or "no-name"
            is_checked = await r.is_checked()
            try:
                label = await self._label_for(r)
            except Exception:
                label = "could not get label"
            is_visible = await r.is_visible()
            self.logger.debug(
                f"Radio {i}: name='{name_attr}', checked={is_checked}, "
                f"visible={is_visible}, label='{label[:80]}'"
            )
        
        # Group radios by name attribute
        groups: Dict[str, List[Locator]] = {}
        
        for i in range(count):
            r = radios.nth(i)
            name = await r.get_attribute("name") or f"group_{i}"
            groups.setdefault(name, []).append(r)
        
        self.logger.debug(f"Found {len(groups)} radio group(s) with {count} total radio buttons")
        
        # Process each group
        for name, items in groups.items():
            self.logger.debug(f"Processing radio group '{name}' with {len(items)} option(s)")
            
            # Logic to handle pre-selected radio buttons
            checked_item = None
            for item in items:
                if await item.is_checked():
                    checked_item = item
                    break
            
            # If an item is already checked and there's only one option,
            # or it's a "deselect" option for a single pre-selected item, skip.
            if checked_item:
                label = await self._label_for(checked_item)
                # Skip if dialog unchanged and we already have a selection
                if is_same_dialog:
                    option_label = await self._get_radio_option_text(checked_item) or label
                    self.logger.info(
                        f"[RADIO_GROUP] Skipping already filled radio group '{name}' "
                        f"(selected='{option_label}') due to unchanged dialog."
                    )
                    continue
                # The assumption here is that if a single option is already checked,
                # no further action is needed. The "deselect" check makes it more robust.
                if len(items) == 1 or 'deselect' in label.lower():
                    self.logger.info(
                        f"Skipping radio group '{name}' as it has a pre-selected "
                        f"and is the only option: '{label}'"
                    )
                    continue
            else:
                self.logger.debug(f"Radio group '{name}' has no pre-selected item, will process it")

            question = await self._infer_group_question(items[0])
            options = []
            option_map = {}  # Map normalized option text to radio locator
            
            for item in items:
                # Use _get_radio_option_text to extract option text (e.g., "Yes", "No")
                # instead of question text
                option_text = await self._get_radio_option_text(item)
                if not option_text:
                    # Fallback: try _label_for, but filter out question text
                    label_text = await self._label_for(item)
                    # If label_text is very long, it's likely the question, not the option
                    # Try to extract just the option part
                    if len(label_text) > 100:
                        # Split by newlines and take the last short line
                        lines = label_text.split('\n')
                        for line in reversed(lines):
                            line = line.strip()
                            if line and len(line) < 50 and 'required' not in line.lower():
                                # Skip question-like lines
                                if not any(word in line.lower() for word in ['are you', 'do you', 'have you']):
                                    option_text = line
                                    break
                    else:
                        option_text = label_text
                
                if option_text:
                    options.append(option_text)
                    # Store mapping for later use when selecting
                    normalized_option = self.normalizer.normalize_string(option_text).lower()
                    option_map[normalized_option] = item
            
            self.logger.info(
                f"[RADIO_GROUP] Processing radio group '{name}': question='{question}', options={options}"
            )
            
            # Call RulesEngine to decide
            self.logger.info(
                f"[RADIO_GROUP] Calling rules_engine.decide for question='{question}', field_type='radio'"
            )
            decision = await self.rules_engine.decide(
                question=question,
                field_type="radio",
                options=options
            )
            self.logger.info(
                f"[RADIO_GROUP] RulesEngine decision: {decision} for question='{question}'"
            )
            selected_option = decision if decision else (options[0] if options else None)
            
            if selected_option:
                normalized_target_option = self.normalizer.normalize_string(selected_option).lower()

                # Log radio group details
                self.logger.debug(
                    f"Radio group '{question}': options={options}, selected='{selected_option}', normalized='{normalized_target_option}'"
                )

                # Find matching option and click using the option_map
                matched_radio = None
                if normalized_target_option in option_map:
                    matched_radio = option_map[normalized_target_option]
                else:
                    # Fallback: try to find by matching normalized option text
                    for item in items:
                        option_text = await self._get_radio_option_text(item)
                        if not option_text:
                            option_text = await self._label_for(item)
                        normalized_label = self.normalizer.normalize_string(option_text).lower()
                        if normalized_label == normalized_target_option:
                            matched_radio = item
                            break
                
                if matched_radio:
                    await matched_radio.check(force=True)
                    # Verify
                    await expect(matched_radio).to_be_checked()
                    self.logger.info(f"Selected radio option '{selected_option}' for question '{question}'")
                else:
                    self.logger.warning(
                        f"Could not find matching radio button for option '{selected_option}' "
                        f"in group '{question}'. Available options: {options}"
                    )
            else:
                self.logger.warning(
                    f"No decision made for radio group '{question}'. Available options: {options}"
                )
    
    async def _handle_checkboxes(self, modal: Locator, is_same_dialog: bool = False):
        """Handle checkbox fields."""
        boxes = modal.get_by_role("checkbox")
        count = await boxes.count()
        
        for i in range(count):
            cb = boxes.nth(i)
            question = await self._compose_checkbox_question(cb)
            
            if is_same_dialog:
                try:
                    if await cb.is_checked():
                        self.logger.info(
                            f"[CHECKBOX] Skipping already filled checkbox for question '{question}' "
                            "due to unchanged dialog."
                        )
                        continue
                except Exception as e:
                    self.logger.debug(f"[CHECKBOX] Could not determine checkbox state: {e}")
            
            # Call RulesEngine to decide
            decision = await self.rules_engine.decide(
                question=question,
                field_type="checkbox",
                options=None
            )
            should_check = bool(decision)
            
            if should_check:
                await cb.check(force=True)
                await expect(cb).to_be_checked()
    
    async def _compose_checkbox_question(self, checkbox: Locator) -> str:
        """
        Build a descriptive question for a checkbox using both legend and label.
        """
        legend_text = await self._extract_checkbox_legend(checkbox)
        label_text = await self._extract_checkbox_label(checkbox)

        parts = []
        if legend_text:
            parts.append(f"legend: {legend_text}")
        if label_text:
            parts.append(f"label: {label_text}")

        if not parts:
            fallback = await self._label_for(checkbox)
            if fallback:
                return fallback
            self.logger.debug("Checkbox question fallback produced empty string.")
            return ""

        return ". ".join(parts)

    async def _extract_checkbox_legend(self, checkbox: Locator) -> str:
        """
        Retrieve legend text associated with a checkbox (if any).
        """
        legend_text = await checkbox.evaluate(
            """(el) => {
                const fieldset = el.closest('fieldset');
                if (!fieldset) return '';
                const legend = fieldset.querySelector('legend');
                if (!legend) return '';
                return legend.innerText ? legend.innerText.trim() : '';
            }"""
        )
        return legend_text or ""

    async def _extract_checkbox_label(self, checkbox: Locator) -> str:
        """
        Retrieve label text associated with a checkbox input.
        """
        label_text = await checkbox.evaluate(
            """(el) => {
                const doc = el.ownerDocument;
                const id = el.id;
                if (!id) return '';

                const escape = doc.defaultView && doc.defaultView.CSS && doc.defaultView.CSS.escape
                    ? doc.defaultView.CSS.escape
                    : (value) => value.replace(/([\\:\\[\\]\\.\\#\\(\\)])/g, '\\\\$1');

                try {
                    const label = doc.querySelector('label[for=\"' + escape(id) + '\"]');
                    if (label && label.innerText) {
                        return label.innerText.trim();
                    }
                } catch (e) {
                    /* ignore */
                }

                const container = el.closest(""" + repr(selectors["data_test_selectable_option"]) + """);
                if (container) {
                    const labelCandidate = container.querySelector('label');
                    if (labelCandidate && labelCandidate.innerText) {
                        return labelCandidate.innerText.trim();
                    }
                }

                return '';
            }"""
        )

        if label_text:
            return label_text

        # Fallback to existing label extraction logic
        fallback = await self._label_for(checkbox)
        return fallback or ""
    
    async def _handle_comboboxes(self, modal: Locator, is_same_dialog: bool = False):
        """Handle combobox and select fields."""
        # Handle custom comboboxes (with listbox)
        combos = modal.get_by_role("combobox").and_(modal.locator(":not(select)"))
        combo_count = await combos.count()
        
        for i in range(combo_count):
            combo = combos.nth(i)
            question = await self._label_for(combo)
            
            if is_same_dialog:
                try:
                    current_value = await combo.input_value()
                    if current_value and current_value.strip():
                        self.logger.info(
                            f"[COMBOBOX] Skipping already filled combobox '{question}' "
                            f"with value '{current_value}' due to unchanged dialog."
                        )
                        continue
                except Exception as e:
                    self.logger.debug(f"[COMBOBOX] Could not determine combobox value: {e}")
            
            await self._process_single_combobox(combo, question, modal, is_same_dialog=is_same_dialog)
        
        # Handle native select elements
        selects = modal.locator("select")  # Using native select tag, not from selectors dict
        select_count = await selects.count()
        
        for i in range(select_count):
            sel = selects.nth(i)
            question = await self._label_for(sel)

            if is_same_dialog:
                try:
                    selected_value = await sel.evaluate("(el) => el.value")
                    if selected_value and str(selected_value).strip():
                        self.logger.info(
                            f"[SELECT] Skipping already filled select '{question}' "
                            f"with value '{selected_value}' due to unchanged dialog."
                        )
                        continue
                    selected_text = await sel.evaluate(
                        "(el) => { const opt = el.options[el.selectedIndex]; return opt ? opt.text : ''; }"
                    )
                    if selected_text and selected_text.strip():
                        self.logger.info(
                            f"[SELECT] Skipping already filled select '{question}' "
                            f"with option '{selected_text}' due to unchanged dialog."
                        )
                        continue
                except Exception as e:
                    self.logger.debug(f"[SELECT] Could not determine select state: {e}")

            options = []
            option_locators = await sel.locator(selectors["select_option"]).all()
            for opt_loc in option_locators:
                opt_text = await opt_loc.inner_text()
                options.append(opt_text)

            decision = await self.rules_engine.decide(
                question=question, field_type="select", options=options
            )

            selected_option = decision if decision else (options[0] if options else None)
            if selected_option:
                normalized_target_option = self.normalizer.normalize_string(
                    selected_option
                )
                found_option_value = None

                for opt_loc in option_locators:
                    current_option_text = await opt_loc.inner_text()
                    normalized_current_option = self.normalizer.normalize_string(
                        current_option_text
                    )

                    if normalized_current_option == normalized_target_option:
                        found_option_value = await opt_loc.get_attribute("value")
                        break

                if found_option_value is not None:
                    await sel.select_option(value=found_option_value)
                else:
                    self.logger.warning(
                        f"Could not find option for '{normalized_target_option}'"
                    )
    
    async def _process_single_combobox(
        self,
        combo: Locator,
        question: str,
        modal: Locator,
        is_same_dialog: bool = False,
    ) -> None:
        """
        Process a single combobox field with improved logic for dynamic listboxes.
        
        This method implements the following algorithm:
        1. Get initial value from RulesEngine
        2. Fill the combobox to trigger the listbox appearance
        3. Wait for and detect the listbox (scoped to modal)
        4. Find best matching option from the listbox
        5. Select the option by clicking on it
        6. Verify the selection was successful
        
        Args:
            combo: Locator for the combobox element
            question: Label/question text for the field
            modal: Locator for the modal dialog (to scope listbox search)
        """
        self.logger.debug(f"Processing combobox: '{question}' (is_same_dialog={is_same_dialog})")
        
        if is_same_dialog:
            try:
                current_value = await combo.input_value()
                if current_value and current_value.strip():
                    self.logger.info(
                        f"[COMBOBOX] Skipping already filled combobox '{question}' "
                        f"with value '{current_value}' due to unchanged dialog."
                    )
                    return
            except Exception as e:
                self.logger.debug(f"[COMBOBOX] Could not determine combobox value inside handler: {e}")
        
        # Step 1: Get initial decision from RulesEngine (without options)
        initial_decision = await self.rules_engine.decide(
            question=question,
            field_type="combobox",
            options=None
        )
        
        if not initial_decision:
            self.logger.warning(f"No decision for combobox '{question}', skipping")
            return
        
        search_text = str(initial_decision).strip()
        self.logger.debug(f"Initial decision for '{question}': '{search_text}'")
        
        # Step 2: Clear and fill the combobox to trigger listbox
        try:
            await combo.click(force=True)
            await combo.clear()
            await combo.fill(search_text)
            
            # Small delay to allow the listbox to appear
            await self.page.wait_for_timeout(300)
            
        except Exception as e:
            self.logger.error(f"Failed to fill combobox '{question}': {e}")
            return
        
        # Step 3: Try to find and wait for the listbox - ONLY IN MODAL
        listbox = None
        
        try:
            # Strategy 1: Try to find LinkedIn-specific typeahead listbox by ID pattern in modal
            # This is the most reliable - LinkedIn uses IDs like "triggered-expanded-emberXXX"
            try:
                typeahead_listbox = modal.locator(selectors["combobox_listbox_id_pattern"])
                listbox_count = await typeahead_listbox.count()
                
                if listbox_count > 0:
                    # Wait for the first (and usually only) visible listbox in modal
                    for i in range(listbox_count):
                        candidate = typeahead_listbox.nth(i)
                        try:
                            if await candidate.is_visible():
                                listbox = candidate
                                self.logger.debug(f"Found LinkedIn typeahead listbox by ID pattern in modal for '{question}'")
                                break
                        except Exception:
                            continue
            except Exception as e:
                self.logger.debug(f"Typeahead listbox by ID pattern search failed: {e}")
            
            # Strategy 2: Try to find listbox by LinkedIn-specific classes in modal
            if not listbox:
                try:
                    class_listbox = modal.locator(
                        selectors["combobox_listbox_class"]
                    )
                    listbox_count = await class_listbox.count()
                    
                    if listbox_count > 0:
                        for i in range(listbox_count):
                            candidate = class_listbox.nth(i)
                            try:
                                if await candidate.is_visible():
                                    listbox = candidate
                                    self.logger.debug(f"Found LinkedIn typeahead listbox by classes in modal for '{question}'")
                                    break
                            except Exception:
                                continue
                except Exception as e:
                    self.logger.debug(f"Typeahead listbox by classes search failed: {e}")
            
            # Strategy 3: Find listbox in modal context (excluding select elements)
            if not listbox:
                try:
                    # Get all listboxes in modal, excluding native select elements
                    modal_listboxes = modal.locator(selectors["combobox_listbox_role"])
                    listbox_count = await modal_listboxes.count()
                    
                    if listbox_count == 1:
                        # Only one listbox in modal - use it
                        listbox = modal_listboxes.first
                        # Verify it's visible
                        if await listbox.is_visible():
                            self.logger.debug(f"Found single listbox in modal for '{question}'")
                        else:
                            listbox = None
                    elif listbox_count > 1:
                        # Multiple listboxes - find the one that's visible and closest to combobox
                        self.logger.debug(f"Found {listbox_count} listboxes in modal, selecting the visible one")
                        
                        for i in range(listbox_count):
                            candidate = modal_listboxes.nth(i)
                            try:
                                if await candidate.is_visible():
                                    # Prefer typeahead listboxes (they have specific classes/IDs)
                                    candidate_id = await candidate.get_attribute("id")
                                    candidate_class = await candidate.get_attribute("class") or ""
                                    
                                    if candidate_id and candidate_id.startswith("triggered-expanded-"):
                                        listbox = candidate
                                        self.logger.debug(f"Selected typeahead listbox by ID '{candidate_id}' for '{question}'")
                                        break
                                    elif "typeahead" in candidate_class or "fb-single-typeahead" in candidate_class:
                                        listbox = candidate
                                        self.logger.debug(f"Selected typeahead listbox by class for '{question}'")
                                        break
                            except Exception:
                                continue
                        
                        # If still no listbox, use first visible one
                        if not listbox:
                            for i in range(listbox_count):
                                candidate = modal_listboxes.nth(i)
                                try:
                                    if await candidate.is_visible():
                                        listbox = candidate
                                        self.logger.debug(f"Selected first visible listbox for '{question}'")
                                        break
                                except Exception:
                                    continue
                except Exception as e:
                    self.logger.debug(f"Modal listbox search failed: {e}")
            
            if not listbox:
                raise Exception("No listbox found in modal context")
            
            # Wait for listbox to be fully visible
            await listbox.wait_for(state="visible", timeout=2000)
            
            # Step 4: Extract all options from the listbox
            options = []
            option_locators = await listbox.get_by_role("option").all()
            
            for opt_loc in option_locators:
                try:
                    opt_text = await opt_loc.inner_text()
                    if opt_text and opt_text.strip():
                        options.append(opt_text.strip())
                except Exception:
                    continue
            
            if not options:
                self.logger.warning(f"Listbox appeared for '{question}' but no options found")
                return
            
            self.logger.debug(f"Found {len(options)} options in listbox for '{question}'")
            
            # Step 5: Find the best matching option
            best_match = self._find_best_match(search_text, options)
            
            if best_match:
                self.logger.info(f"Selected option '{best_match}' for '{question}'")
                
                # Click on the matching option
                try:
                    # Try to find option by exact text match (case-insensitive)
                    option_found = False
                    for opt_loc in option_locators:
                        try:
                            opt_text = await opt_loc.inner_text()
                            if opt_text and opt_text.strip().lower() == best_match.lower():
                                await opt_loc.click(timeout=1000)
                                option_found = True
                                break
                        except Exception:
                            continue
                    
                    # If exact match not found, try contains match
                    if not option_found:
                        for opt_loc in option_locators:
                            try:
                                opt_text = await opt_loc.inner_text()
                                if opt_text and best_match.lower() in opt_text.lower():
                                    await opt_loc.click(timeout=1000)
                                    option_found = True
                                    break
                            except Exception:
                                continue
                    
                    if not option_found:
                        self.logger.error(f"Failed to click option '{best_match}' - option not found in listbox")
                        return
                        
                except Exception as e:
                    self.logger.error(f"Failed to click option '{best_match}': {e}")
                    return
                
                # Step 6: Wait for listbox to close and verify the value was set
                await self.page.wait_for_timeout(300)
                try:
                    # Wait for listbox to disappear (indicates selection was successful)
                    await listbox.wait_for(state="hidden", timeout=2000)
                except Exception:
                    # Listbox might not disappear immediately, that's okay
                    pass
                
                try:
                    current_value = await combo.input_value()
                    self.logger.debug(f"Combobox '{question}' value after selection: '{current_value}'")
                except Exception:
                    pass
                
            else:
                self.logger.warning(f"No matching option found in listbox for '{search_text}'")
                
        except Exception as e:
            # Listbox did not appear or was not found - treat as a simple text input
            self.logger.warning(
                f"Combobox '{question}' did not open a listbox in modal (timeout or error). "
                f"Treating as a textbox. Error: {e}"
            )
            
            # The value is already filled from Step 2, so we're done
            # But let's make sure it's there
            try:
                current_value = await combo.input_value()
                if not current_value or current_value != search_text:
                    await combo.fill(search_text)
                    self.logger.debug(f"Filled combobox '{question}' as textbox with '{search_text}'")
            except Exception as fill_error:
                self.logger.error(f"Failed to fill combobox '{question}' as textbox: {fill_error}")
    
    def _find_best_match(self, search_text: str, options: List[str]) -> Optional[str]:
        """
        Find the best matching option from a list based on search text.
        
        Algorithm:
        1. Exact match (case-insensitive)
        2. Starts with search text (case-insensitive)
        3. Contains search text (case-insensitive)
        4. First option as fallback
        
        Args:
            search_text: Text to search for
            options: List of available options
            
        Returns:
            Best matching option or None if no options
        """
        if not options:
            return None
        
        if not search_text:
            return options[0] if options else None
        
        search_lower = search_text.lower().strip()
        
        # Try exact match
        for opt in options:
            if opt.lower().strip() == search_lower:
                self.logger.debug(f"Exact match found: '{opt}'")
                return opt
        
        # Try starts with
        for opt in options:
            if opt.lower().strip().startswith(search_lower):
                self.logger.debug(f"Starts-with match found: '{opt}'")
                return opt
        
        # Try contains
        for opt in options:
            if search_lower in opt.lower():
                self.logger.debug(f"Contains match found: '{opt}'")
                return opt
        
        # No match found - return first option as fallback
        self.logger.debug(f"No match found for '{search_text}', using first option: '{options[0]}'")
        return options[0]

    async def _handle_number_inputs(self, modal: Locator, is_same_dialog: bool = False):
        """Handle number input fields (input[type='number'])."""
        # Find all number inputs using CSS selector since they don't have textbox role
        number_inputs = modal.locator(selectors["number_input"])
        count = await number_inputs.count()
        
        self.logger.debug(f"Found {count} number input(s)")
        
        for i in range(count):
            num_input = number_inputs.nth(i)
            question = await self._label_for(num_input)
            
            if is_same_dialog:
                try:
                    current_value = await num_input.input_value()
                    if current_value and current_value.strip():
                        self.logger.info(
                            f"[NUMBER] Skipping already filled number input '{question}' "
                            f"with value '{current_value}' due to unchanged dialog."
                        )
                        continue
                except Exception as e:
                    self.logger.debug(f"[NUMBER] Could not determine number input value: {e}")
            
            # Get additional attributes for debugging
            placeholder = await num_input.get_attribute("placeholder") or ""
            required = await num_input.get_attribute("required") or ""
            name_attr = await num_input.get_attribute("name") or ""
            min_val = await num_input.get_attribute("min") or ""
            max_val = await num_input.get_attribute("max") or ""
            
            # Log the extracted question and attributes for debugging
            self.logger.debug(f"Number input {i+1}/{count}: question='{question}', name='{name_attr}', required={bool(required)}, min={min_val}, max={max_val}")
            
            # Call RulesEngine to decide
            decision = await self.rules_engine.decide(
                question=question,
                field_type="number",
                options=None
            )
            value = decision if decision else "0"
            
            self.logger.debug(f"Number input '{question}': decision={decision}, final_value={value}")
            
            # Convert to integer if possible
            if isinstance(value, (int, float)):
                value = str(int(value))
            elif str(value).replace(".", "").isdigit():
                value = str(int(float(value)))
            else:
                value = "0"
            
            await num_input.fill(value)
    
    async def _handle_textboxes(self, modal: Locator, is_same_dialog: bool = False):
        """Handle text input fields."""
        # Find all textboxes, but exclude elements that also have the "combobox" role,
        # as they are handled separately and might not be fillable.
        tbs = modal.get_by_role("textbox").and_(
            modal.locator(':not([role="combobox"])')
        )
        count = await tbs.count()
        
        for i in range(count):
            tb = tbs.nth(i)
            question = await self._label_for(tb)
            
            if is_same_dialog:
                try:
                    current_value = await tb.input_value()
                    if current_value and current_value.strip():
                        self.logger.info(
                            f"[TEXTBOX] Skipping already filled textbox '{question}' "
                            f"with value '{current_value[:50]}' due to unchanged dialog."
                        )
                        continue
                except Exception:
                    try:
                        current_value = await tb.inner_text()
                        if current_value and current_value.strip():
                            self.logger.info(
                                f"[TEXTBOX] Skipping already filled textbox '{question}' "
                                f"(textarea content) due to unchanged dialog."
                            )
                            continue
                    except Exception as e:
                        self.logger.debug(f"[TEXTBOX] Could not determine textbox value: {e}")
            
            # Get additional attributes for debugging
            placeholder = await tb.get_attribute("placeholder") or ""
            required = await tb.get_attribute("required") or ""
            name_attr = await tb.get_attribute("name") or ""
            
            # Log the extracted question and attributes for debugging
            self.logger.debug(f"Textbox {i+1}/{count}: question='{question}', placeholder='{placeholder}', name='{name_attr}', required={bool(required)}")
            
            # Determine field type
            input_type = (await tb.get_attribute("type") or "").lower()
            inputmode = (await tb.get_attribute("inputmode") or "").lower()
            field_type = "number" if (input_type == "number" or inputmode in ("numeric", "decimal")) else "text"
            
            # Call RulesEngine to decide
            decision = await self.rules_engine.decide(
                question=question,
                field_type=field_type,
                options=None
            )
            value = decision if decision else ("N/A" if field_type == "text" else "0")
            
            self.logger.debug(f"Textbox '{question}': decision={decision}, final_value={value}")
            
            if field_type == "number":
                value = str(int(value) if str(value).isdigit() else 0)
            
            await tb.fill(str(value))
    
    async def _infer_group_question(self, any_radio: Locator) -> str:
        """
        Infer the question text for a radio group.
        
        Args:
            any_radio: Any radio button from the group
            
        Returns:
            Question text
        """
        # Try aria-labelledby first
        labelledby = await any_radio.get_attribute("aria-labelledby")
        if labelledby:
            text = await any_radio.evaluate(
                """(el) => {
                    const id = el.getAttribute('aria-labelledby');
                    const lbl = el.ownerDocument.getElementById(id);
                    return lbl ? lbl.innerText : '';
                }"""
            )
            if text:
                return text.strip()
        
        # Try fieldset legend
        legend = any_radio.locator(selectors["xpath_ancestor_fieldset_legend"])
        if await legend.count():
            # New: Try to find a specific title span within the legend for robustness
            title_span = legend.first.locator(
                selectors["radio_form_builder_title"]
            )
            if await title_span.count() > 0:
                return (await title_span.first.inner_text()).strip()

            # Fallback to the original behavior if the specific span isn't found
            return (await legend.first.inner_text()).strip()

        # Fallback to aria-label
        aria = await any_radio.get_attribute("aria-label")
        return aria or "radio group"
    
    async def _get_radio_option_text(self, radio: Locator) -> str:
        """
        Extract option text for a radio button (not the question text).
        
        For radio buttons, we need the text of the specific option (e.g., "Yes", "No"),
        not the question text from the fieldset legend.
        
        Args:
            radio: Radio button locator
            
        Returns:
            Option text (e.g., "Yes", "No")
        """
        # Try to find the label element that contains the option text
        # LinkedIn radio buttons are usually structured as:
        # <label><input type="radio"> Option Text </label>
        # or
        # <li><input type="radio"><span>Option Text</span></li>
        
        try:
            # Method 1: Get text from parent container, excluding the input and filtering question text
            option_text = await radio.evaluate(
                """(el) => {
                    // Find parent container (label, li, or div with radio class)
                    let container = el.closest('label, li, div[class*="radio"], div[class*="option"]');
                    if (!container) container = el.parentElement;
                    if (!container) return '';
                    
                    // Clone to avoid modifying original
                    const clone = container.cloneNode(true);
                    
                    // Remove all radio inputs from clone
                    const inputs = clone.querySelectorAll('input[type="radio"]');
                    inputs.forEach(input => input.remove());
                    
                    // Get text and split by newlines
                    const text = clone.innerText.trim();
                    const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                    
                    // Find lines that look like options (short, not questions)
                    const questionWords = ['are you', 'do you', 'have you', 'can you', 'will you', 'required'];
                    const optionLines = lines.filter(line => {
                        const lower = line.toLowerCase();
                        // Skip lines that contain question words or are too long
                        const hasQuestionWord = questionWords.some(word => lower.includes(word));
                        const isTooLong = line.length > 80;
                        const hasRequired = lower.includes('required') && lines.length > 1;
                        return !hasQuestionWord && !isTooLong && !(hasRequired && line.length < 10);
                    });
                    
                    if (optionLines.length > 0) {
                        // Return the shortest line (most likely the option text like "Yes", "No")
                        const shortest = optionLines.reduce((a, b) => a.length < b.length ? a : b);
                        // Remove "Required" suffix if present
                        return shortest.replace(/\\s+Required\\s*$/i, '').trim();
                    }
                    
                    // Fallback: if we have lines, try the last short line
                    if (lines.length > 0) {
                        for (let i = lines.length - 1; i >= 0; i--) {
                            const line = lines[i];
                            if (line.length > 0 && line.length < 50 && 
                                !line.toLowerCase().includes('required') &&
                                !questionWords.some(word => line.toLowerCase().includes(word))) {
                                return line;
                            }
                        }
                    }
                    
                    // Last resort: return first non-empty line if text is not too long
                    if (text.length < 50) {
                        return text;
                    }
                    
                    return '';
                }"""
            )
            
            if option_text and option_text.strip():
                cleaned = option_text.strip()
                # Remove common suffixes
                cleaned = re.sub(r'\s+Required\s*$', '', cleaned, flags=re.IGNORECASE)
                if cleaned:
                    return cleaned
        except Exception as e:
            self.logger.debug(f"Error extracting radio option text (method 1): {e}")
        
        # Method 2: Try to find sibling span or label with option text
        try:
            sibling_text = await radio.evaluate(
                """(el) => {
                    // Look for next sibling span, label, or div
                    let sibling = el.nextElementSibling;
                    let attempts = 0;
                    while (sibling && attempts < 5) {
                        const tagName = sibling.tagName;
                        if (tagName === 'SPAN' || tagName === 'LABEL' || tagName === 'DIV') {
                            const text = sibling.innerText.trim();
                            // Skip if it looks like a question
                            if (text && text.length < 50 && 
                                !text.toLowerCase().includes('are you') &&
                                !text.toLowerCase().includes('do you') &&
                                !text.toLowerCase().includes('required')) {
                                return text;
                            }
                        }
                        sibling = sibling.nextElementSibling;
                        attempts++;
                    }
                    return '';
                }"""
            )
            if sibling_text and sibling_text.strip():
                cleaned = sibling_text.strip()
                cleaned = re.sub(r'\s+Required\s*$', '', cleaned, flags=re.IGNORECASE)
                if cleaned:
                    return cleaned
        except Exception as e:
            self.logger.debug(f"Error extracting radio option text (method 2): {e}")
        
        # Method 3: Try aria-label (should be option-specific if present)
        try:
            aria = await radio.get_attribute("aria-label")
            if aria and aria.strip():
                aria_clean = aria.strip()
                # If aria-label is short and doesn't look like a question, use it
                if len(aria_clean) < 50 and not any(word in aria_clean.lower() for word in ['are you', 'do you', 'have you']):
                    return aria_clean
        except Exception:
            pass
        
        # Method 4: Try value attribute (sometimes contains the option text)
        try:
            value = await radio.get_attribute("value")
            if value and value.strip():
                return value.strip()
        except Exception:
            pass
        
        # Fallback: return empty string (caller should handle this)
        return ""
    
    async def _label_for(self, element: Locator) -> str:
        """
        Extract label text for an element.
        
        Uses multiple strategies to find label text:
        1. Standard ARIA attributes (aria-label, aria-labelledby)
        2. Label[for] association
        3. Fieldset legend
        4. LinkedIn-specific data-test attributes
        5. Parent container text
        6. Previous sibling text
        7. Common LinkedIn form field patterns
        
        Args:
            element: Element locator
            
        Returns:
            Label text
        """
        # Try aria-label
        aria = await element.get_attribute("aria-label")
        if aria and aria.strip():
            return aria.strip()
        
        # Try aria-labelledby
        labelledby = await element.get_attribute("aria-labelledby")
        if labelledby:
            text = await element.evaluate(
                """(el) => {
                    const id = el.getAttribute('aria-labelledby');
                    if (!id) return '';
                    return id.split(' ')
                        .map(id => el.ownerDocument.getElementById(id))
                        .filter(Boolean)
                        .map(n => n.innerText)
                        .join(' ').trim();
                }"""
            )
            if text and text.strip():
                return text.strip()
        
        # Try label[for] association
        lab_text = await element.evaluate(
            """(el) => {
                const id = el.id;
                if (!id) return '';
                const lbl = el.ownerDocument.querySelector(`label[for="${id}"]`);
                return lbl ? lbl.innerText : '';
            }"""
        )
        if lab_text and lab_text.strip():
            return lab_text.strip()

        # Try parent fieldset legend
        legend_text = await element.evaluate(
            """(el) => {
                const fieldset = el.closest('fieldset');
                if (!fieldset) return '';
                const legend = fieldset.querySelector('legend');
                return legend ? legend.innerText : '';
            }"""
        )
        if legend_text and legend_text.strip():
            return legend_text.strip()
        
        # Try LinkedIn-specific data-test attributes
        # Look for span with data-test attributes that contain label text
        try:
            data_test_label = element.locator(
                selectors["xpath_ancestor_form_field"]
            )
            if await data_test_label.count() > 0:
                label_text = await data_test_label.first.inner_text()
                if label_text and label_text.strip():
                    return label_text.strip()
        except Exception:
            pass
        
        # Try to find label text in parent container
        # Look for text in parent div/span that appears before the input
        try:
            parent_label_text = await element.evaluate(
                """(el) => {
                    // Find parent container (form field wrapper)
                    let parent = el.closest('div[class*="form"], div[class*="field"], div[class*="input"], li, fieldset');
                    if (!parent) parent = el.parentElement;
                    if (!parent) return '';
                    
                    // Get all potential label elements in the parent
                    const labelSelectors = ['label', 'span', 'div', 'p'];
                    const candidates = [];
                    
                    for (const selector of labelSelectors) {
                        const elements = parent.querySelectorAll(selector);
                        for (const candidate of elements) {
                            // Skip the input element itself and its children
                            if (candidate === el || candidate.contains(el)) {
                                continue;
                            }
                            
                            const text = candidate.innerText.trim();
                            if (text && text.length > 0 && text.length < 100) {
                                // Skip error messages and validation text
                                const lowerText = text.toLowerCase();
                                if (lowerText.includes('error') || 
                                    lowerText.includes('invalid') || 
                                    lowerText.includes('required') ||
                                    lowerText.includes('please enter')) {
                                    continue;
                                }
                                
                                // Skip if it contains the input value or placeholder
                                const inputValue = (el.value || el.placeholder || '').toLowerCase();
                                if (inputValue && inputValue.length > 0 && lowerText.includes(inputValue)) {
                                    continue;
                                }
                                
                                // Check if this element is before the input in DOM order
                                try {
                                    const position = candidate.compareDocumentPosition(el);
                                    if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
                                        candidates.push({
                                            text: text,
                                            element: candidate,
                                            isBefore: true
                                        });
                                    }
                                } catch (e) {
                                    // If compareDocumentPosition fails, still add as candidate
                                    candidates.push({
                                        text: text,
                                        element: candidate,
                                        isBefore: false
                                    });
                                }
                            }
                        }
                    }
                    
                    // Sort candidates: prefer elements that are before the input
                    candidates.sort((a, b) => {
                        if (a.isBefore && !b.isBefore) return -1;
                        if (!a.isBefore && b.isBefore) return 1;
                        // Prefer shorter text (more likely to be a label)
                        return a.text.length - b.text.length;
                    });
                    
                    // Return the first candidate
                    if (candidates.length > 0) {
                        return candidates[0].text;
                    }
                    
                    return '';
                }"""
            )
            if parent_label_text and parent_label_text.strip():
                return parent_label_text.strip()
        except Exception:
            pass
        
        # Try to find text in previous sibling elements
        try:
            sibling_label_text = await element.evaluate(
                """(el) => {
                    // Look for previous sibling that might contain label text
                    let sibling = el.previousElementSibling;
                    while (sibling) {
                        const text = sibling.innerText.trim();
                        // Skip if text is too long or empty
                        if (text && text.length > 0 && text.length < 100) {
                            // Check if it looks like a label (not an error message)
                            if (!text.toLowerCase().includes('error') && 
                                !text.toLowerCase().includes('invalid') &&
                                !text.toLowerCase().includes('required')) {
                                return text;
                            }
                        }
                        sibling = sibling.previousElementSibling;
                    }
                    return '';
                }"""
            )
            if sibling_label_text and sibling_label_text.strip():
                return sibling_label_text.strip()
        except Exception:
            pass
        
        # Try to find label by walking up DOM tree (up to 5 levels)
        # Extract and combine text from adjacent elements before the input
        try:
            dom_walk_label = await element.evaluate(
                """(el) => {
                    // Walk up the DOM tree up to 5 levels from the input element
                    let inputContainer = el;
                    const allGroups = [];
                    
                    // Walk up to 5 levels
                    for (let level = 1; level <= 5; level++) {
                        if (!inputContainer || !inputContainer.parentElement) break;
                        
                        // Move to parent
                        const parent = inputContainer.parentElement;
                        
                        // Get all children of parent
                        const children = Array.from(parent.children);
                        
                        // Find which child contains (or is) the input container
                        let inputChildIndex = -1;
                        for (let i = 0; i < children.length; i++) {
                            if (children[i].contains(el) || children[i] === inputContainer) {
                                inputChildIndex = i;
                                break;
                            }
                        }
                        
                        // If we found the input container's position, collect all elements before it
                        if (inputChildIndex > 0) {
                            const elementsBeforeInput = [];
                            
                            for (let i = 0; i < inputChildIndex; i++) {
                                const candidate = children[i];
                                
                                // Skip if candidate contains the input
                                if (candidate.contains(el)) {
                                    continue;
                                }
                                
                                // Extract text from candidate element
                                try {
                                    let text = candidate.textContent || candidate.innerText || '';
                                    text = text.trim();
                                    
                                    if (text && text.length > 0) {
                                        // Skip if it's exactly the input value
                                        const inputValue = (el.value || el.placeholder || '').trim();
                                        if (inputValue && text === inputValue) {
                                            continue;
                                        }
                                        
                                        // Store element with its text and position
                                        elementsBeforeInput.push({
                                            text: text,
                                            index: i
                                        });
                                    }
                                } catch (e) {
                                    continue;
                                }
                            }
                            
                            // If we found elements before input at this level, group adjacent elements
                            if (elementsBeforeInput.length > 0) {
                                // Group consecutive elements (adjacent elements)
                                const groups = [];
                                let currentGroup = [];
                                
                                for (let i = 0; i < elementsBeforeInput.length; i++) {
                                    const elem = elementsBeforeInput[i];
                                    
                                    if (currentGroup.length === 0) {
                                        // Start new group
                                        currentGroup.push(elem);
                                    } else {
                                        // Check if this element is adjacent to the last element in current group
                                        const lastIndex = currentGroup[currentGroup.length - 1].index;
                                        if (elem.index === lastIndex + 1) {
                                            // Adjacent element - add to current group
                                            currentGroup.push(elem);
                                        } else {
                                            // Not adjacent - save current group and start new one
                                            if (currentGroup.length > 0) {
                                                groups.push([...currentGroup]);
                                            }
                                            currentGroup = [elem];
                                        }
                                    }
                                }
                                
                                // Don't forget the last group
                                if (currentGroup.length > 0) {
                                    groups.push(currentGroup);
                                }
                                
                                // Process each group: combine texts and calculate distance from input
                                for (const group of groups) {
                                    // Combine texts from all elements in the group
                                    const combinedTexts = group.map(e => e.text).filter(t => t && t.length > 0);
                                    if (combinedTexts.length > 0) {
                                        // Join texts with dot and space between them
                                        const combinedText = combinedTexts.join('. ').trim();
                                        
                                        if (combinedText.length > 0) {
                                            // Calculate distance from input
                                            // Distance = inputChildIndex - lastElementIndex (how many elements between group and input)
                                            const lastElementIndex = group[group.length - 1].index;
                                            const distance = inputChildIndex - lastElementIndex;
                                            
                                            // Store group with distance
                                            allGroups.push({
                                                text: combinedText,
                                                distance: distance,
                                                level: level
                                            });
                                        }
                                    }
                                }
                            }
                        }
                        
                        // Update inputContainer for next iteration
                        inputContainer = parent;
                    }
                    
                    // Sort groups by distance only (closer to input = smaller distance = higher priority)
                    allGroups.sort((a, b) => {
                        return a.distance - b.distance;
                    });
                    
                    // Return the text from the closest group (first after sorting)
                    if (allGroups.length > 0) {
                        return allGroups[0].text;
                    }
                    
                    return '';
                }"""
            )
            if dom_walk_label and dom_walk_label.strip():
                return dom_walk_label.strip()
        except Exception:
            pass
        
        # Try to extract label from preceding siblings by walking up DOM tree
        try:
            sibling_label = await self._extract_label_from_siblings(element)
            if sibling_label and sibling_label.strip():
                return sibling_label.strip()
        except Exception as e:
            self.logger.debug(f"Failed to extract label from siblings: {e}")
            
        # Last resort: return "field" but log a warning
        try:
            element_id = await element.get_attribute('id')
            element_name = await element.get_attribute('name')
            element_type = await element.get_attribute('type')
            element_placeholder = await element.get_attribute('placeholder')
            self.logger.warning(
                f"Could not extract label for element. Using fallback 'field'. "
                f"Element attributes: id={element_id}, "
                f"name={element_name}, "
                f"type={element_type}, "
                f"placeholder={element_placeholder}"
            )
        except Exception:
            self.logger.warning("Could not extract label for element. Using fallback 'field'.")
        return "field"
    
    async def _extract_label_from_siblings(self, element: Locator) -> str:
        """
        Extract label by walking up DOM tree and collecting text from preceding siblings.
        
        This method:
        1. Walks up to 6 levels from the input element
        2. At each level, collects all preceding siblings
        3. Extracts all text from each sibling at any depth
        4. Filters texts (length, error markers, input value matches)
        5. Combines texts from siblings at the same level through ". "
        6. Groups candidates by distance and selects minimum distance
        7. Combines texts from all candidates with minimum distance
        
        Args:
            element: Element locator (input field)
            
        Returns:
            Combined label text or empty string
        """
        return await element.evaluate("""
            (el) => {
                function extractAllText(node) {
                    // Skip script, style, and hidden elements
                    if (node.nodeType === Node.TEXT_NODE) {
                        return node.textContent.trim();
                    }
                    if (node.nodeType !== Node.ELEMENT_NODE) return '';
                    
                    const tagName = node.tagName.toLowerCase();
                    if (tagName === 'script' || tagName === 'style') return '';
                    
                    // Check if element is hidden
                    const style = window.getComputedStyle(node);
                    if (style.display === 'none' || style.visibility === 'hidden') {
                        return '';
                    }
                    
                    // Recursively extract text from all children
                    let text = '';
                    for (let child of node.childNodes) {
                        text += ' ' + extractAllText(child);
                    }
                    return text.trim();
                }
                
                function cleanText(text) {
                    if (!text) return '';
                    return text.replace(/\\s+/g, ' ').trim();
                }
                
                function isValidLabelText(text, inputEl) {
                    if (!text || text.length === 0) return false;
                    if (text.length > 200) return false;
                    
                    const lowerText = text.toLowerCase();
                    const errorMarkers = ['error', 'invalid', 'required', 'please enter'];
                    if (errorMarkers.some(marker => lowerText.includes(marker))) {
                        return false;
                    }
                    
                    const inputValue = (inputEl.value || inputEl.placeholder || '').trim();
                    if (inputValue && text.toLowerCase() === inputValue.toLowerCase()) {
                        return false;
                    }
                    
                    return true;
                }
                
                function removeDuplicates(texts) {
                    const seen = new Set();
                    const unique = [];
                    for (let text of texts) {
                        const normalized = text.toLowerCase().trim();
                        if (normalized && !seen.has(normalized)) {
                            seen.add(normalized);
                            unique.push(text);
                        }
                    }
                    return unique;
                }
                
                let current = el;
                const candidates = [];
                
                // Walk up to 6 levels
                for (let level = 1; level <= 6; level++) {
                    if (!current || !current.parentElement) break;
                    
                    const parent = current.parentElement;
                    const siblings = Array.from(parent.children);
                    
                    // Find index of element containing input
                    let inputIndex = -1;
                    for (let i = 0; i < siblings.length; i++) {
                        if (siblings[i].contains(el) || siblings[i] === current) {
                            inputIndex = i;
                            break;
                        }
                    }
                    
                    if (inputIndex <= 0) {
                        current = parent;
                        continue;
                    }
                    
                    // Collect all preceding siblings
                    const precedingSiblings = siblings.slice(0, inputIndex);
                    const texts = [];
                    
                    for (let sibling of precedingSiblings) {
                        const text = extractAllText(sibling);
                        const cleanedText = cleanText(text);
                        
                        if (isValidLabelText(cleanedText, el)) {
                            texts.push(cleanedText);
                        }
                    }
                    
                    if (texts.length > 0) {
                        const combinedText = texts.join('. ');
                        candidates.push({
                            text: combinedText,
                            level: level,
                            distance: inputIndex
                        });
                    }
                    
                    current = parent;
                }
                
                if (candidates.length === 0) {
                    return '';
                }
                
                // Find minimum distance
                const minDistance = Math.min(...candidates.map(c => c.distance));
                
                // Select all candidates with minimum distance
                const bestCandidates = candidates.filter(c => c.distance === minDistance);
                
                // Combine their texts through ". "
                const combinedLabels = bestCandidates
                    .map(c => c.text)
                    .filter(t => t && t.length > 0);
                
                // Remove duplicates (if same text found on different levels)
                const uniqueLabels = removeDuplicates(combinedLabels);
                
                return uniqueLabels.join('. ');
            }
        """)
    
    async def _wait_for_spinners_to_disappear(self, timeout: int = 5000):
        """Wait for all loading spinners to disappear."""
        spinners = self.page.locator(selectors["loading_spinner"])
        count = await spinners.count()
        
        for i in range(count):
            try:
                spinner = spinners.nth(i)
                await spinner.wait_for(state="hidden", timeout=timeout)
            except Exception:
                # Spinner might have already disappeared
                pass
    
    async def _safe_click(self, button: Locator):
        """
        Safely click a button with verification.
        
        Args:
            button: Button locator
        """
        # Wait for button to be enabled and visible
        await expect(button).to_be_visible()
        await expect(button).to_be_enabled()
        
        # Click
        await button.click()
        
        # Wait for button to become disabled or detached (prevents double-click)
        try:
            await button.wait_for(state="detached", timeout=1000)
        except Exception:
            # Button might not detach, try disabled state
            try:
                await expect(button).to_be_disabled(timeout=1000)
            except Exception:
                # Button might remain enabled, that's okay
                pass
    
    async def _wait_for_modal_transition(self, old_modal: Locator, timeout: int = 5000):
        """
        Wait for modal transition to complete.
        
        Args:
            old_modal: Locator for the old modal
            timeout: Maximum wait time in milliseconds
        """
        try:
            # Wait for old modal to be detached from DOM
            await old_modal.wait_for(state="detached", timeout=timeout)
        except Exception:
            # If old modal doesn't detach, wait for spinners to disappear
            await self._wait_for_spinners_to_disappear(timeout=timeout)
