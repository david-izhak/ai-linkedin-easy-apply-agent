# LLM Prompt Templates

# Prompt for calculating the skill match to a job vacancy
VACANCY_MATCH_PROMPT = """You are a strict scoring engine. Follow the algorithm exactly, without subjective judgments or randomness. Do not infer unstated skills. Use only explicit evidence from inputs.

INPUTS:
Job Description:
{vacancy_description}

Candidate skills from resume:
{resume_text}

ALGORITHM (deterministic):

1) NORMALIZATION
- Lowercase all text, remove diacritics, trim spaces.
- Split skills on commas, semicolons, slashes, pipes, and newlines; also detect common multi-word tech phrases.
- Canonicalize tokens using the fixed synonyms map (apply left→right):
  {{
  "java":"javascript",
  "ts":"typescript",
  "py":"python",
  "postgres":"postgresql",
  "ms sql":"sql server",
  "k8s":"kubernetes",
  "ci/cd":"cicd",
  "aws":"amazon web services",
  "gcp":"google cloud platform",
  "azure":"microsoft azure",
  "s3":"aws s3",
  "eks":"aws eks",
  "gke":"google kubernetes engine",
  "aks":"azure kubernetes service",
  "db":"database",
  "oop":"object oriented programming",
  "rest api":"rest",
  "dotnet":".net",
  "node":"node.js",
  "reactjs":"react",
  "js":"javascript",
  "pg":"postgresql",
  "mongo":"mongodb",
  "mq":"message queue",
  "spark":"apache spark"
  }}
- After mapping, deduplicate skills. Sort lists alphabetically before scoring.

2) EXTRACT REQUIREMENTS FROM JOB
- Mark a skill as REQUIRED if it appears in a clearly mandatory context containing any of:
  ["must","required","necessarily", "obligatorily","требуется","mandatory","necessary"].
- Mark as OPTIONAL if under contexts like:
  ["nice to have","desirable","will be a plus","preferred","optional"].
- If context is unclear, treat as OPTIONAL.
- If no REQUIRED skills are found, the required set is empty.

3) EXTRACT CANDIDATE SKILLS
- Include only explicit skills/tech/tools/platforms/methodologies found verbatim (after normalization).
- Do not assume equivalents beyond the synonyms map.

4) EXPERIENCE & SENIORITY
- Parse required years of experience from job text; if none found, treat as not required.
- Parse candidate total years if stated in resume.
- Seniority levels mapping (ascending): intern=0, junior=1, middle=2, mid=2, senior=3, lead=4, principal=5, staff=5, architect=5.
  If multiple appear, take the highest per text.
- If a level is missing on either side, skip that subcomponent as neutral (see step 6).

5) MATCHING RULE
- A skill matches iff candidate_skill == job_skill after normalization OR both map to the same canonical token via the synonyms map. No semantic similarity beyond this.

6) SUBSCORES (all in [0,1])
- Required skills recall: req_sub = 1 if |REQ|=0 else (matched_required / |REQ|)
- Optional skills recall: opt_sub = 0 if |OPT|=0 else (matched_optional / |OPT|)
- Experience:
  - Years: years_sub = 1 if no required years; else min(1, candidate_years / required_years) if candidate_years present; else 0
  - Seniority: sen_sub = 1 if job level missing; else if candidate level present then 1 if cand_level >= job_level else (cand_level+1)/(job_level+1); else 0
  - exp_sub = 0.7*years_sub + 0.3*sen_sub
- Education/Certs (if explicitly required): edu_sub = 1 if all explicitly required degrees/certs are present in resume; if some missing → matched/required; if none required → 1.

7) WEIGHTS (sum to 1)
REQ_WEIGHT=0.45, OPT_WEIGHT=0.35, EXP_WEIGHT=0.15, EDU_WEIGHT=0.05

8) TOTAL SCORE
raw = REQ_WEIGHT*req_sub + OPT_WEIGHT*opt_sub + EXP_WEIGHT*exp_sub + EDU_WEIGHT*edu_sub
match_percentage = round_half_up(100 * raw). Clamp to [0,100].
round_half_up rule: fractions of 0.5 round away from zero (e.g., 84.5 → 85).

9) OUTPUT (STRICT JSON, deterministic)
- Return a single JSON object exactly matching the schema below. No extra commentary.
{{
  "match_percentage": <integer 0..100>,
  "analysis": "Required: X/Y matched; Optional: U/V matched; Exp: cand {C}y vs req {R}y; Seniority: cand {CL} vs req {RL}.",
  "required": {
    "total": <integer Y>,
    "matched_count": <integer X>,
    "missing_count": <integer Y - X>,
    "matched": ["<skill1>", "<skill2>", ...],   // normalized, unique, alphabetically sorted
    "missing": ["<skill1>", "<skill2>", ...]    // normalized, unique, alphabetically sorted
  },
  "optional": {
    "total": <integer V>,
    "matched_count": <integer U>,
    "missing_count": <integer V - U>,
    "matched": ["<skill1>", "<skill2>", ...],   // normalized, unique, alphabetically sorted
    "missing": ["<skill1>", "<skill2>", ...]    // normalized, unique, alphabetically sorted
  },
  "experience": {
    "required_years": <integer or null>,
    "candidate_years": <integer or null>,
    "required_seniority": "<one of: intern|junior|middle|senior|lead|principal|staff|architect or null>",
    "candidate_seniority": "<one of: intern|junior|middle|senior|lead|principal|staff|architect or null>"
  }
}}
- Consistency requirements (CRITICAL):
  - required.total == len(required.matched) + len(required.missing)
  - required.matched_count == len(required.matched)
  - required.missing_count == len(required.missing)
  - optional.total == len(optional.matched) + len(optional.missing)
  - optional.matched_count == len(optional.matched)
  - optional.missing_count == len(optional.missing)
  - All lists deduplicated and alphabetically sorted.
  - Use normalized/canonicalized skill tokens for list entries.

FAILURE HANDLING
- If either input is empty or non-informative, set match_percentage to 0, analysis to "Insufficient input to compute a deterministic score.", and return empty arrays with zero counts for required/optional and nulls for experience.

Based on the algorithm, perform the scoring now."""

# Prompt to generate a cover letter
COVER_LETTER_PROMPT = """
**ROLE:**
You are an AI assistant specialized in writing professional cover letters.

**CONTEXT:**

---
**JOB INFORMATION:**
- **Job Title:** {job_title}
- **Company:** {company_name}
- **Location:** {location}
- **Job Description:** {description}
- **Employment Type:** {employment_type}

---
**COMPANY INFORMATION:**
- **Company Description:** {company_description}
- **Company Overview:** {company_overview}
- **Website:** {company_website}
- **Company Industry:** {company_industry}
- **Company Size:** {company_size}

---
**CANDIDATE'S RESUME:**
{resume_text}
---

**INSTRUCTIONS:**

Based on the context provided, write a professional and compelling cover letter.

1.  **Personalization:** Tailor the letter specifically to the company and the job role.
2.  **Highlight Match:** Clearly connect the candidate's skills and experiences from the resume to the job description's requirements. Use 2-3 specific, measurable achievements from the resume.
3.  **Demonstrate Interest:** Show genuine understanding of and enthusiasm for the company.
4.  **Tone & Style:** Maintain a professional and concise tone. Avoid clichés. The letter should be between 320 and 420 words, structured in 3-5 short paragraphs.
5.  **Optional:** Include a P.S. and links only if `include_ps` or `include_links` is true.

Your task is to generate the content for the cover letter.
"""


COVER_LETTER_PROMPT_STRUCTURED = """### ROLE ###
You are a master AI assistant specializing in writing professional, tailored cover letters.

### TASK ###
Generate a compelling cover letter by synthesizing the provided context. You must follow all instructions and output requirements precisely.

### OUTPUT STRUCTURE ###
Your entire response MUST be a single JSON object matching the structure below. Do not add any text, comments, or markdown formatting before or after the JSON.
```json
{{
  "greeting": "string",
  "paragraphs": [
    "string (paragraph 1, >=40 words)",
    "string (paragraph 2, >=40 words)",
    "string (paragraph 3, >=40 words)"
  ],
  "closing": "string",
  "signature": "string (Candidate Name and contact info)",
  "ps": "string or null"
}}
```

### CONTEXT ###

**1. Job Information:**
- **Title:** {job_title}
- **Company:** {company_name}
- **Location:** {location}
- **Description:** {description}
- **Type:** {employment_type}

**2. Company Information:**
- **Description:** {company_description}
- **Overview:** {company_overview}
- **Website:** {company_website}
- **Industry:** {company_industry}
- **Size:** {company_size}

**3. Candidate's Resume:**
```
{resume_text}
```

**4. Contextual Flags:**
- `include_ps`: {include_ps}
- `include_links`: {include_links}

### INSTRUCTIONS & RULES ###

**I. Output Requirements (CRITICAL):**
- **Format:** Adhere strictly to the JSON structure provided above.
- **`paragraphs` Field:**
  - MUST be an array of 3 to 5 strings.
  - Each string in the array MUST be a substantial paragraph of **at least 40 words**. This is a strict requirement.
- **`signature` Field:**
  - MUST contain the candidate's full name and contact details (e.g., phone, email).
  - DO NOT put the main letter content or closing remarks here.

**II. Content Guidelines:**
- **Personalization:** Tailor the letter specifically to the company and the job role. Show genuine understanding of the company.
- **Highlight Achievements:** Connect the candidate's resume to the job description by highlighting 2-3 specific, measurable achievements.

**III. Style and Tone:**
- **Tone:** Professional, confident, and concise.
- **Length:** The total word count for all paragraphs combined should be between 320 and 420 words.
- **P.S.:** Only add content to the `ps` field if the `include_ps` flag is `true`. Otherwise, it must be `null`.

**IV. Language Skills Guidelines (CRITICAL):**
- **Hebrew:** Do NOT mention Hebrew language proficiency or level in the cover letter, even if Hebrew is required in the job description or mentioned in the resume.
- **English:** Always mention that the candidate has professional-level English proficiency. This should be included naturally in one of the paragraphs when discussing communication skills or qualifications.
- **Russian:** Always mention that the candidate has native-level Russian proficiency. This should be included naturally when discussing language skills or qualifications.
- **Other Languages:** Only mention other languages if they are explicitly required in the job description and are clearly mentioned in the resume with a strong proficiency level.
"""


FIELD_DECISION_ENGINE_PROMPT = """ROLE: Field Decision Engine

POLICY:
- Use ONLY candidate_profile and field_context provided.
- Return STRICT JSON format matching the LLMDecision schema.
- No invented facts. Respect type, min/max, maxlength, available options.
- Set confidence to a float between 0.0 (total guess) and 1.0 (certain).
- If confidence is low (< 0.8), make an optimistic guess. For questions about willingness, agreement, or for boolean/checkbox fields, always choose the affirmative/positive option (e.g., "Yes", "Agree", check the box).

OUTPUT FORMAT:
{
  "decision": "select|text|number|check|skip",
  "value": <appropriate value>,
  "confidence": <0.0-1.0>,
  "suggest_rule": null
}

NOTE: Rule generation is handled separately after the decision is made. Leave suggest_rule as null.

**SPECIAL CASE - Combobox/Autocomplete Fields:**
When field_type is "combobox" (autocomplete with dynamic options), provide the FULL, COMPLETE value that should appear in the dropdown.
For example, for "Location (city)" with candidate in "Rishon LeZion", provide the full format like "Rishon LeZion, Center District, Israel".
This value will be used to search in the dynamic dropdown list.

TEMPERATURE: 0 (deterministic output required)"""


RULE_GENERATION_PROMPT = """ROLE: Rule Generation Engine

Your task is to generate a reusable rule for form field filling based on the provided context.

TASK:
Generate a rule that can be used to automatically fill similar fields in the future.

RULE STRUCTURE:
The rule must contain:
1. q_pattern: A regex pattern that matches the question text (case-insensitive)
   - Should capture key phrases/words that identify this field type
   - Examples: "(python|питон)" for Python skill checkbox, "(visa|work authorization)" for visa questions
   - Use named capture groups if you need to extract dynamic values (e.g., skill name)
   - Pattern should be specific enough to match this field type but general enough to work for similar questions
   - For multilingual support, include both English and Russian variants in the pattern

2. strategy: Defines how to fill the field
   - kind: One of: "literal", "profile_key", "numeric_from_profile", "one_of_options", "one_of_options_from_profile", "salary_by_currency"
   - params: Strategy-specific parameters

STRATEGY SELECTION GUIDE:

- Checkbox fields (boolean):
  Use "literal" strategy with value: true/false
  Example: {"kind": "literal", "params": {"value": true}}
  REQUIRED: "value" must be present in params

- Text fields with profile data:
  Use "profile_key" strategy with appropriate key from candidate profile
  Example: {"kind": "profile_key", "params": {"key": "address.city"}}
  Common keys: address.city, address.country, phone, email, links.github, links.linkedin, personal.firstName, personal.lastName
  REQUIRED: "key" must be present in params and must be a valid profile key path

- Number fields with profile data:
  Use "numeric_from_profile" strategy with key path
  Example: {"kind": "numeric_from_profile", "params": {"key": "years_experience.python"}}
  For dynamic skill extraction, use named capture groups: {"kind": "numeric_from_profile", "params": {"key": "years_experience.{skill}"}}
  REQUIRED: "key" must be present in params and must point to a numeric field in the profile (e.g., "years_experience.python")

- Radio/Select fields with fixed options:
  Use "one_of_options" strategy with preferred option OR synonyms
  Example 1 (simple): {"kind": "one_of_options", "params": {"preferred": ["Yes", "Да"]}}
  Example 2 (with synonyms): {"kind": "one_of_options", "params": {"synonyms": {"Yes": ["Yes", "Да", "yes"], "No": ["No", "Нет", "no"]}}}
  REQUIRED: Either "preferred" (list of preferred options) OR "synonyms" (map of canonical values to synonyms) must be present in params
  NOTE: "preferred" is a list of option values that should be selected. "synonyms" is a map for matching options with variations.

- Radio/Select fields with profile-based selection:
  Use "one_of_options_from_profile" strategy with profile key and synonyms
  Example 1 (language): {"kind": "one_of_options_from_profile", "params": {"key": "languages[0].language", "synonyms": {"English": ["English", "английский"], "Hebrew": ["Hebrew", "иврит"], "Russian": ["Russian", "русский"]}}}
  Example 2 (work authorization): {"kind": "one_of_options_from_profile", "params": {"key": "work_authorization.US", "synonyms": {"yes": ["Yes", "Да", "U.S. Citizen"], "no": ["No", "Нет"], "need_visa": ["Need Visa", "Требуется виза"]}}}
  Example 3 (gender): {"kind": "one_of_options_from_profile", "params": {"key": "equalOpportunity.gender", "synonyms": {"Male": ["Male", "Мужской"], "Female": ["Female", "Женский"], "Decline": ["Decline", "Prefer not to say", "Не указывать"]}}}
  REQUIRED: "key" must be present in params and must point to a field in the profile
  RECOMMENDED: "synonyms" should be present to map profile values to form options. If omitted, the system will try to match the profile value directly.

- Salary fields:
  Use "salary_by_currency" strategy
  Example: {"kind": "salary_by_currency", "params": {"base_key_template": "salary_expectation.monthly_net_{currency}", "default_currency": "nis"}}
  REQUIRED: Both "base_key_template" and "default_currency" must be present in params

EXAMPLES:

1. Checkbox "Python":
   q_pattern: "(python|питон)"
   strategy: {"kind": "literal", "params": {"value": true}}
   NOTE: "value" is REQUIRED

2. Text field "Location (city)":
   q_pattern: "(location.*city|city|город)"
   strategy: {"kind": "profile_key", "params": {"key": "address.city"}}
   NOTE: "key" is REQUIRED and must be a valid profile path

3. Number field "Years of experience with Python":
   q_pattern: "(years? of experience.*python|опыт.*python)"
   strategy: {"kind": "numeric_from_profile", "params": {"key": "years_experience.python"}}
   NOTE: "key" is REQUIRED and must point to a numeric field in profile.years_experience

4. Number field with dynamic skill extraction:
   q_pattern: "(?P<skill>python|java|javascript).*years? of experience"
   strategy: {"kind": "numeric_from_profile", "params": {"key": "years_experience.{skill}"}}
   NOTE: Use named capture groups in pattern and reference them in key with {group_name}

5. Radio "Willing to relocate" (simple Yes/No):
   q_pattern: "(relocate|willing to relocate|готовность к переезду)"
   strategy: {"kind": "one_of_options", "params": {"preferred": ["Yes", "Да"]}}
   NOTE: "preferred" is a list of option values to select from

6. Radio "Willing to relocate" (with synonyms):
   q_pattern: "(relocate|willing to relocate|готовность к переезду)"
   strategy: {"kind": "one_of_options", "params": {"synonyms": {"Yes": ["Yes", "Да", "Willing"], "No": ["No", "Нет", "Not willing"]}}}
   NOTE: "synonyms" maps canonical values to lists of possible option variations

7. Select "Native language speaker" (profile-based):
   q_pattern: "(native|родной).*?(?P<language>hebrew|иврит|english|английский|russian|русский).*?speaker"
   strategy: {"kind": "one_of_options_from_profile", "params": {"key": "languages[0].language", "synonyms": {"English": ["English", "английский"], "Hebrew": ["Hebrew", "иврит"], "Russian": ["Russian", "русский"]}}}
   NOTE: "key" is REQUIRED (points to profile field), "synonyms" is RECOMMENDED (maps profile values to form options)

8. Select "Gender" (profile-based):
   q_pattern: "(gender|how do you identify|пол)"
   strategy: {"kind": "one_of_options_from_profile", "params": {"key": "equalOpportunity.gender", "synonyms": {"Male": ["Male", "Мужской"], "Female": ["Female", "Женский"], "Decline": ["Decline", "Prefer not to say", "Не указывать"]}}}
   NOTE: Check the candidate profile for the actual field structure and values

9. Combobox "Location (city)":
   q_pattern: "(location.*city|city|город)"
   strategy: {"kind": "profile_key", "params": {"key": "address.city"}}

10. Select "Email":
    q_pattern: "(email|e-mail|электронная почта)"
    strategy: {"kind": "profile_key", "params": {"key": "email"}}

11. Text field "Phone":
    q_pattern: "(phone|телефон)"
    strategy: {"kind": "profile_key", "params": {"key": "phone"}}

OUTPUT FORMAT:
Return a JSON object with the following structure:
{
  "q_pattern": "<regex pattern>",
  "strategy": {
    "kind": "<strategy_kind>",
    "params": {<strategy_params>}
  },
  "confidence": <0.0-1.0>
}

CRITICAL REQUIREMENTS:
1. The "strategy" field MUST be a complete object with both "kind" and "params" fields.
2. The "kind" field MUST be one of the valid strategy kinds: "literal", "profile_key", "numeric_from_profile", "one_of_options", "one_of_options_from_profile", "salary_by_currency"
3. The "params" field MUST be a dictionary (object) with strategy-specific parameters.
4. DO NOT return an empty "strategy": {} object. Always provide a complete strategy definition.
5. DO NOT return empty "params": {} for strategies that require parameters. Always fill in the required params.

REQUIRED PARAMS BY STRATEGY KIND:
- "literal": MUST have "value" (boolean or string)
- "profile_key": MUST have "key" (string, profile field path)
- "numeric_from_profile": MUST have "key" (string, profile field path to numeric value)
- "one_of_options": MUST have either "preferred" (list of strings) OR "synonyms" (map of strings to lists)
- "one_of_options_from_profile": MUST have "key" (string, profile field path), SHOULD have "synonyms" (map)
- "salary_by_currency": MUST have "base_key_template" (string) and "default_currency" (string)

VALIDATION RULES:
- If strategy kind is "one_of_options" and params is empty or missing "preferred"/"synonyms", the rule will be REJECTED
- If strategy kind is "numeric_from_profile" and params is empty or missing "key", the rule will be REJECTED
- If strategy kind is "one_of_options_from_profile" and params is empty or missing "key", the rule will be REJECTED
- If strategy kind is "profile_key" and params is empty or missing "key", the rule will be REJECTED

STRATEGY FIELD REQUIREMENTS (QUICK REFERENCE):
- For checkbox fields: {"kind": "literal", "params": {"value": true/false}}
- For text fields: {"kind": "profile_key", "params": {"key": "email"}}
- For number fields: {"kind": "numeric_from_profile", "params": {"key": "years_experience.python"}}
- For radio/select fields (simple): {"kind": "one_of_options", "params": {"preferred": ["Yes", "Да"]}}
- For radio/select fields (with synonyms): {"kind": "one_of_options", "params": {"synonyms": {"Yes": ["Yes", "Да"], "No": ["No", "Нет"]}}}
- For radio/select fields (profile-based): {"kind": "one_of_options_from_profile", "params": {"key": "languages[0].language", "synonyms": {"English": ["English"], "Hebrew": ["Hebrew"]}}}

IMPORTANT:
- The q_pattern should be specific enough to match this field type but general enough to work for similar questions
- Use case-insensitive matching (regex flags are handled by the system)
- For multilingual support, include both English and Russian variants in the pattern
- Confidence should reflect how confident you are that this rule will work for similar fields
- Minimum confidence for rule acceptance is 0.85
- Patterns should be between 3 and 200 characters
- Avoid overly generic patterns like ".*" or ".*.*"
- Use named capture groups for dynamic value extraction when appropriate
- ALWAYS provide a complete strategy object with both "kind" and "params" fields. Never return an empty strategy object."""