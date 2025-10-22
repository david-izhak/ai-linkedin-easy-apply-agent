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
  {{"java":"javascript","ts":"typescript","py":"python","postgres":"postgresql","ms sql":"sql server","k8s":"kubernetes","ci/cd":"cicd","aws":"amazon web services","gcp":"google cloud platform","azure":"microsoft azure","s3":"aws s3","eks":"aws eks","gke":"google kubernetes engine","aks":"azure kubernetes service","db":"database","oop":"object oriented programming","rest api":"rest","dotnet":".net","node":"node.js","reactjs":"react","js":"javascript","pg":"postgresql","mongo":"mongodb","mq":"message queue","spark":"apache spark"}}
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
REQ_WEIGHT=0.60, OPT_WEIGHT=0.20, EXP_WEIGHT=0.15, EDU_WEIGHT=0.05

8) TOTAL SCORE
raw = REQ_WEIGHT*req_sub + OPT_WEIGHT*opt_sub + EXP_WEIGHT*exp_sub + EDU_WEIGHT*edu_sub
match_percentage = round_half_up(100 * raw). Clamp to [0,100].
round_half_up rule: fractions of 0.5 round away from zero (e.g., 84.5 → 85).

9) ANALYSIS STRING (deterministic format)
- At most 2 short sentences, ≤300 characters total.
- Sentence 1: "Required: X/Y matched; missing: [names alphabetically or 'none']."
- Sentence 2: "Optional: U/V matched; Exp: cand {{C}}y vs req {{R}}y; Seniority: cand {{CL}} vs req {{RL}}."
- Use "n/a" when a value is not available.

FAILURE HANDLING
- If either input is empty or non-informative, calculate a match_percentage of 0 and use the analysis "Insufficient input to compute a deterministic score."

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
- **Job Level:** {seniority_level}
- **Employment Type:** {employment_type}
- **Field:** {job_function}
- **Industries:** {industries}

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


COVER_LETTER_PROMPT_STRUCTURED = """
You are an AI assistant specialized in writing professional cover letters.
Return output ONLY via structured fields (greeting, paragraphs[3-5], closing, signature, optional ps).
Plain text only — no markdown, no code blocks, no headers. 320–420 words total.

CONTEXT:
JOB: {job_title} @ {company_name}, {location}
LEVEL: {seniority_level} | TYPE: {employment_type} | FUNCTION: {job_function} | INDUSTRIES: {industries}

JOB DESCRIPTION:
{description}

COMPANY:
{company_description}
{company_overview}
Website: {company_website} | Industry: {company_industry} | Size: {company_size}

CANDIDATE RESUME:
{resume_text}

RULES:
- CRITICAL: Return a structured response. The 'paragraphs' field must be an array of 3 to 5 separate strings.
- Personalize to the role/company.
- Highlight 2–3 concrete achievements tied to the job requirements.
- Professional, concise tone. 3–5 short paragraphs.
- Add P.S. only if include_ps=true in context. Do not add links unless include_links=true.
"""