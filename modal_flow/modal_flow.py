"""
ModalFlowRunner: Main orchestrator for filling LinkedIn Easy Apply modal forms.

This module implements the core logic for parsing modals, applying rules,
resolving fields, and controlling the flow between multiple modal steps.
"""

import re
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from playwright.async_api import Page, Locator, expect

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
SPINNER_SELECTOR = '[aria-busy="true"], [data-loading="true"]'
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
        logger: Optional[logging.Logger] = None
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
        
        for step in range(max_steps):
            self.logger.info(f"Processing step {step + 1}/{max_steps}")
            
            # Wait for spinners to disappear
            await self._wait_for_spinners_to_disappear()
            
            # Find active modal
            modal = await self._active_modal()
            if not modal:
                self.logger.info("No active modal found. Ending run.")
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
            
            # Fill all fields in current modal
            await self._fill_modal(modal)
            
            # Check for Submit button first (higher priority)
            submit_btn = modal.get_by_role("button", name=SUBMIT_BTN_RX).first
            if await submit_btn.is_visible():
                if should_submit:
                    self.logger.info("Submit button found, clicking.")
                    await self._safe_click(submit_btn)
                    self.logger.info("Submit button clicked. Flow finished.")
                    submitted = True
                else:
                    self.logger.info(
                        "Submit button found, skipping click due to DRY RUN mode."
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
                    parent = error.locator('xpath=ancestor::*[@class or @id][1]')
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
    
    async def _fill_modal(self, modal: Locator):
        """
        Fill all fields in the current modal.
        
        Args:
            modal: Locator for the modal dialog
        """
        self.logger.debug("Filling modal fields")
        
        # Attach documents if required before filling other fields
        if self._document_uploader:
            await self._document_uploader.handle_modal(modal)

        # Process fields in order: radio groups, checkboxes, comboboxes, number inputs, textboxes
        await self._handle_radio_groups(modal)
        await self._handle_checkboxes(modal)
        await self._handle_comboboxes(modal)
        await self._handle_number_inputs(modal)
        await self._handle_textboxes(modal)
    
    async def _handle_radio_groups(self, modal: Locator):
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
            
            for item in items:
                label = await self._label_for(item)
                options.append(label)
            
            self.logger.info(
                f"Processing radio group '{name}': question='{question}', options={options}"
            )
            
            # Call RulesEngine to decide
            decision = await self.rules_engine.decide(
                question=question,
                field_type="radio",
                options=options
            )
            selected_option = decision if decision else (options[0] if options else None)
            
            normalized_target_option = self.normalizer.normalize_string(selected_option)

            # Log radio group details
            self.logger.debug(
                f"Radio group '{question}': options={options}, selected='{selected_option}', normalized='{normalized_target_option}'"
            )

            # Find matching option index and click
            for item in items:
                label = await self._label_for(item)
                normalized_label = self.normalizer.normalize_string(label)
                if normalized_label == normalized_target_option:
                    await item.check(force=True)
                    # Verify
                    await expect(item).to_be_checked()
                    break
    
    async def _handle_checkboxes(self, modal: Locator):
        """Handle checkbox fields."""
        boxes = modal.get_by_role("checkbox")
        count = await boxes.count()
        
        for i in range(count):
            cb = boxes.nth(i)
            label = await self._label_for(cb)
            
            # Call RulesEngine to decide
            decision = await self.rules_engine.decide(
                question=label,
                field_type="checkbox",
                options=None
            )
            should_check = bool(decision)
            
            if should_check:
                await cb.check(force=True)
                await expect(cb).to_be_checked()
    
    async def _handle_comboboxes(self, modal: Locator):
        """Handle combobox and select fields."""
        # Handle custom comboboxes (with listbox)
        combos = modal.get_by_role("combobox").and_(modal.locator(":not(select)"))
        combo_count = await combos.count()
        
        for i in range(combo_count):
            combo = combos.nth(i)
            question = await self._label_for(combo)
            await self._process_single_combobox(combo, question)
        
        # Handle native select elements
        selects = modal.locator("select")
        select_count = await selects.count()
        
        for i in range(select_count):
            sel = selects.nth(i)
            question = await self._label_for(sel)

            options = []
            option_locators = await sel.locator("option").all()
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
    
    async def _process_single_combobox(self, combo: Locator, question: str) -> None:
        """
        Process a single combobox field with improved logic for dynamic listboxes.
        
        This method implements the following algorithm:
        1. Get initial value from RulesEngine
        2. Fill the combobox to trigger the listbox appearance
        3. Wait for and detect the listbox
        4. Find best matching option from the listbox
        5. Select the option by clicking on it
        6. Verify the selection was successful
        
        Args:
            combo: Locator for the combobox element
            question: Label/question text for the field
        """
        self.logger.debug(f"Processing combobox: '{question}'")
        
        # Step 1: Get initial decision from RulesEngine (without options)
        # This will use rules or delegate to LLM if no rule matches
        initial_decision = await self.rules_engine.decide(
            question=question,
            field_type="combobox",
            options=None  # We don't have options yet
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
        
        # Step 3: Try to find and wait for the listbox
        try:
            listbox = self.page.get_by_role("listbox")
            await listbox.wait_for(state="visible", timeout=2000)
            
            # Step 4: Extract all options from the listbox
            options = []
            option_locators = await listbox.get_by_role("option").all()
            
            for opt_loc in option_locators:
                try:
                    opt_text = await opt_loc.inner_text()
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
                    # Try exact match first
                    await listbox.get_by_role("option", name=re.compile(f"^{re.escape(best_match)}$")).first.click(timeout=1000)
                except Exception:
                    # Fallback to contains match
                    try:
                        await listbox.get_by_role("option").filter(has_text=best_match).first.click(timeout=1000)
                    except Exception as e:
                        self.logger.error(f"Failed to click option '{best_match}': {e}")
                        return
                
                # Step 6: Verify the value was set
                await self.page.wait_for_timeout(200)
                try:
                    current_value = await combo.input_value()
                    self.logger.debug(f"Combobox '{question}' value after selection: '{current_value}'")
                except Exception:
                    pass
                
            else:
                self.logger.warning(f"No matching option found in listbox for '{search_text}'")
                
        except Exception as e:
            # Listbox did not appear - treat as a simple text input
            self.logger.warning(
                f"Combobox '{question}' did not open a listbox (timeout or error). "
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

    async def _handle_number_inputs(self, modal: Locator):
        """Handle number input fields (input[type='number'])."""
        # Find all number inputs using CSS selector since they don't have textbox role
        number_inputs = modal.locator('input[type="number"]')
        count = await number_inputs.count()
        
        self.logger.debug(f"Found {count} number input(s)")
        
        for i in range(count):
            num_input = number_inputs.nth(i)
            question = await self._label_for(num_input)
            
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
    
    async def _handle_textboxes(self, modal: Locator):
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
        legend = any_radio.locator("xpath=ancestor::fieldset[1]/legend")
        if await legend.count():
            # New: Try to find a specific title span within the legend for robustness
            title_span = legend.first.locator(
                "span[data-test-form-builder-radio-button-form-component__title]"
            )
            if await title_span.count() > 0:
                return (await title_span.first.inner_text()).strip()

            # Fallback to the original behavior if the specific span isn't found
            return (await legend.first.inner_text()).strip()

        # Fallback to aria-label
        aria = await any_radio.get_attribute("aria-label")
        return aria or "radio group"
    
    async def _label_for(self, element: Locator) -> str:
        """
        Extract label text for an element.
        
        Args:
            element: Element locator
            
        Returns:
            Label text
        """
        # Try aria-label
        aria = await element.get_attribute("aria-label")
        if aria:
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
            if text:
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

        # Fallback to parent fieldset legend
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
            
        return "field"
    
    async def _wait_for_spinners_to_disappear(self, timeout: int = 5000):
        """Wait for all loading spinners to disappear."""
        spinners = self.page.locator(SPINNER_SELECTOR)
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
