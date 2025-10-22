# LOGIN DETAILS
LINKEDIN_EMAIL = "itskovdi@gmail.com"
LINKEDIN_PASSWORD = "e_r_G186vCqo"  # <-- ВАЖНО: Введите ваш пароль здесь

# SESSION DATA
USER_DATA_DIR = "./linkedin_session"

# JOB SEARCH PARAMETERS
KEYWORDS = "Software Engineer"
GEO_ID = "118490091"  # Geo ID for a specific location (e.g., Israel)
DISTANCE = "20"  # Search radius in miles/km depending on LinkedIn's interpretation
# Default time filter for the very first run (in seconds). 2592000 = 30 days.
DEFAULT_JOB_POSTED_FILTER_SECONDS = 2592000
# Sort by: DD = Date Descending (most recent), R = Relevance
SORT_BY = "DD"
WORKPLACE = {
    "REMOTE": True,
    "ON_SITE": True,
    "HYBRID": True,
}
# Regular expression for job titles
# JOB_TITLE = r".*(software|backend|java|python|data|back|end|ai|chatbot|principal|Fullstack|Full|stack).*(developer|engineer).*"
JOB_TITLE = r"^(?!.*(technical|lead|teamlead|devops|salesforce|technology|llm)).*(software|backend|java|python|data|back|end|ai|chatbot|principal|Fullstack|Full|stack).*(developer|engineer).*$"
# Regular expression to exclude certain terms in job descriptions (e.g., "primeit")
# JOB_DESCRIPTION = r"^((?!(teamlead))(.|[\\n\\r]))*$"
JOB_DESCRIPTION = r".*"
# List of accepted languages for job descriptions. Use ["any"] to accept all.
JOB_DESCRIPTION_LANGUAGES = ["english", "russian", "hebrew"]

# FORM DATA
PHONE = "535487266"
CV_PATH = "D:/py/linkedin-easy-apply-bot/CV_David_Izhak_Software_Engineer.pdf"  # <-- ВАЖНО: Укажите путь к вашему резюме
COVER_LETTER_PATH = ""  # <-- Укажите путь к сопроводительному письму, если есть
HOME_CITY = "Rishon LeZion, Israel"
YEARS_OF_EXPERIENCE = {
    "spring": 7,
    "java": 7,
    "mongodb": 3,
    "kubernetes": 3,
    "CI/CD": 5,
    "python": 3,
    "html": 7,
    "google cloud": 2,
    "docker": 5,
    "css": 7,
    "typescript": 3,
    "aws": 3,
    "gcp": 2,
    "azure": 2,
    "kafka": 5,
    "rabbitmq": 3,
    "rest": 7,
    "sql": 7,
    "microservices": 5,
    "jpa": 6,
    "mvc": 4,
    "jdbc": 4,
    "hibernate": 4,
    "junit": 5,
    "mockito": 3,
    "lombok": 7,
    "grpc": 2,
    "json": 6,
    "maven": 5,
    "gradle": 5,
    "pip": 3,
    "poetry": 2,
    "uv": 1,
    "testcontainers": 2,
    "liquibase": 3,
    "spark": 2,
    "agents": 2,
    "mcp": 2,
    "fastmcp": 2,
    "langchain": 1,
    "langgraph": 1,
    "bots": 1,
    "etl": 3,
    "elt": 3,
    "postman": 7,
    "protobuf": 2,
    "swagger": 2,
    "telegram": 2,
    "helm": 4,
    "kubectl": 5,
    "k9s": 4,
    "kibana": 5,
    "grafana": 3,
    "prometheus": 5,
    "elasticsearch": 3,
    "bash": 7,
    "artifactory": 3,
    "jenkins": 4,
    "databricks": 2,
    "ec2": 4,
    "s3": 3,
    "lambda": 2,
    "gpts": 2,
    "cassandra": 2,
    "scylladb": 2,
    "postgresql": 6,
    "mysql": 6,
    "sqlite": 4,
    "redis": 3,
    "firebase": 2,
    "dynamodb": 2,
    "agile": 7,
    "jira": 7,
}
LANGUAGE_PROFICIENCY = {
    "english": "professional",
    "russian": "native",
    "hebrew": "beginner",
}
REQUIRES_VISA_SPONSORSHIP = False
TEXT_FIELDS = {"salary": "35k"}  # Примерное значение, измените при необходимости
BOOLEANS = {"bachelhor|bacharelado": True, "authorized": True}
MULTIPLE_CHOICE_FIELDS = {"pronouns": "He/him"}

# OTHER SETTINGS
SINGLE_PAGE = False
BROWSER_HEADLESS = False
LOG_LEVEL = "DEBUG"  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
MAX_APPLICATIONS_PER_DAY = 30  # Daily limit for job applications
WAIT_BETWEEN_APPLICATIONS = (
    30000  # Time in milliseconds to wait between job applications
)

# BOT OPERATING MODE
# "discovery": Only fetch job links and save to DB.
# "enrichment": Fetch job links, save to DB, then enrich discovered jobs with details.
# "processing": Only process (apply to) jobs that are already enriched in DB.
# "full_run": Perform all steps: discovery -> enrichment -> processing.
BOT_MODE = "full_run"
