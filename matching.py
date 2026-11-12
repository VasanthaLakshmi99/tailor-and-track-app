"""Skill-based match score (no AI, no internet).

How it works:
1. Find the known SKILLS mentioned in the JD (AWS, Kubernetes, Terraform, ...).
   Company words, benefits and HR text are ignored.
2. Skills mentioned more often in the JD count more (max 3x).
3. Score = skills found in your resume / skills in the JD, as a percent.
4. Missing = JD skills not in your resume (add only what is true for you).

Different spellings count as the same skill: "k8s" = "Kubernetes",
"Amazon Web Services" = "AWS", "CI/CD" = "continuous integration", etc.
This is an estimate to sort jobs - not an employer's ATS score.
"""
VERSION = "2026-11-03a"   # all Tailor&Track files must have the same version
import functools
import re

# canonical name: other spellings
SKILLS = {
    # cloud
    "AWS": ["amazon web services"], "Azure": ["microsoft azure"], "GCP": ["google cloud", "google cloud platform"],
    "EC2": [], "S3": [], "IAM": [], "VPC": [], "Lambda": ["aws lambda"], "RDS": ["amazon rds"],
    "DynamoDB": [], "CloudFormation": ["cloud formation"], "CloudWatch": [], "Route 53": ["route53"],
    "EKS": ["amazon eks", "elastic kubernetes service"], "ECS": ["elastic container service"], "Fargate": [],
    "AKS": [], "GKE": [], "ECR": [], "SNS": [], "SQS": [], "API Gateway": [], "ELB": ["load balancer", "load balancers"],
    "CodePipeline": [], "CodeBuild": [], "CodeDeploy": [], "Systems Manager": ["ssm"], "Secrets Manager": [],
    "OpenStack": [], "VMware": [],
    # devops / platform
    "Docker": ["containers", "containerization", "containerized"], "Kubernetes": ["k8s"], "Helm": [],
    "OpenShift": [], "Rancher": [], "Istio": ["service mesh"], "Terraform": [], "Terragrunt": [],
    "Ansible": [], "Puppet": [], "Chef": [], "SaltStack": [], "Packer": [], "Vagrant": [], "Vault": ["hashicorp vault"],
    "Consul": [], "Pulumi": [], "Infrastructure as Code": ["iac"],
    "CI/CD": ["ci cd", "cicd", "ci/cd pipelines", "continuous integration", "continuous delivery", "continuous deployment"],
    "Jenkins": [], "GitLab CI": ["gitlab", "gitlab-ci"], "GitHub Actions": [], "Azure DevOps": ["azure pipelines", "vsts"],
    "Bamboo": [], "TeamCity": [], "CircleCI": [], "Travis CI": [], "ArgoCD": ["argo cd", "argo"], "Flux": ["fluxcd"],
    "GitOps": [], "DevSecOps": [], "SRE": ["site reliability", "site reliability engineering"],
    "Git": ["github", "bitbucket"], "Maven": [], "Gradle": [], "Nexus": [], "Artifactory": ["jfrog"],
    "SonarQube": ["sonar"], "Trivy": [], "Snyk": [],
    "Prometheus": [], "Grafana": [], "Datadog": [], "New Relic": ["newrelic"], "Splunk": [], "Nagios": [],
    "ELK": ["elk stack"], "Elasticsearch": ["elastic search"], "Logstash": [], "Kibana": [], "Fluentd": [],
    "Dynatrace": [], "AppDynamics": [], "PagerDuty": [], "OpenTelemetry": [], "Observability": ["monitoring"],
    "Linux": ["rhel", "red hat", "ubuntu", "centos"], "Unix": [], "Windows Server": [],
    "Bash": ["shell scripting", "shell scripts", "shell"], "PowerShell": [],
    "Nginx": [], "Apache": [], "Tomcat": [], "Networking": ["tcp/ip", "dns", "dhcp", "firewalls", "subnets"],
    "Microservices": ["micro services", "microservice"], "Serverless": [],
    # languages
    "Python": ["boto3"], "Java": [], "JavaScript": [], "TypeScript": [], "Node.js": ["nodejs", "node js"],
    "Golang": ["go lang"], "Ruby": [], "Scala": [], "C#": [], "C++": [], ".NET": ["dotnet", "asp.net"],
    "PHP": [], "Rust": [], "Kotlin": [], "Swift": [], "R": [],
    # data
    "SQL": ["t-sql", "pl/sql"], "NoSQL": [], "MySQL": [], "PostgreSQL": ["postgres"], "Oracle": [], "SQL Server": ["mssql"],
    "MongoDB": ["mongo"], "Cassandra": [], "Redis": [], "Kafka": ["apache kafka"], "RabbitMQ": [],
    "Spark": ["apache spark", "pyspark"], "Hadoop": ["hdfs"], "Hive": [], "Airflow": ["apache airflow"],
    "Snowflake": [], "Databricks": [], "dbt": [], "Redshift": [], "BigQuery": [], "Glue": ["aws glue"],
    "Athena": [], "EMR": [], "Kinesis": [], "ETL": ["elt"], "Data Warehouse": ["data warehousing"],
    "Data Lake": ["lakehouse", "delta lake"], "Data Modeling": ["data modelling", "dimensional modeling"],
    "Informatica": [], "Talend": [], "SSIS": [], "Tableau": [], "Power BI": ["powerbi"], "Looker": [],
    "Pandas": [], "NumPy": [], "Machine Learning": ["ml"], "MLOps": [],
    # web / apps
    "React": ["react.js", "reactjs"], "Angular": [], "Vue": ["vue.js"], "Spring Boot": ["spring"],
    "Django": [], "Flask": [], "FastAPI": [], "REST API": ["rest", "restful", "rest apis"], "GraphQL": [],
    # ways of working
    "Agile": ["scrum", "kanban"], "Jira": [], "Confluence": [], "ITIL": [], "ServiceNow": [],
    "Security": ["cybersecurity", "security best practices"], "High Availability": ["disaster recovery"],
}

# words that are too common in normal English to use when they stand alone
AMBIGUOUS = {"r", "shell", "spring", "rest", "argo", "flux", "vault", "glue", "go lang",
             "monitoring", "containers", "security", "load balancer", "dns", "ml", "apache", "oracle", "swift"}


# more roles: QA, Salesforce, SAP, business analyst, security, network, full stack, AI, mobile
SKILLS.update({
    "Selenium": [], "Cypress": [], "Playwright": [], "Appium": [], "TestNG": [], "JUnit": [], "Mockito": [],
    "Cucumber": ["bdd"], "Postman": [], "JMeter": [], "LoadRunner": [], "Manual Testing": [],
    "Automation Testing": ["test automation", "automated testing"], "API Testing": [], "Regression Testing": [],
    "Performance Testing": ["load testing"], "UAT": ["user acceptance testing"], "Test Cases": ["test case", "test plans", "test plan"],
    "Salesforce": ["sfdc"], "Apex": [], "Visualforce": [], "Lightning": ["lwc", "lightning web components"],
    "Sales Cloud": [], "Service Cloud": [], "SOQL": [],
    "SAP": [], "ABAP": ["sap abap"], "SAP FICO": ["fico"], "SAP MM": [], "SAP SD": [], "S/4HANA": ["s4hana", "s/4 hana", "hana"],
    "Business Analysis": ["business analyst"], "Requirements Gathering": ["requirement gathering", "brd", "frd"],
    "User Stories": ["user story"], "Stakeholder Management": [], "Process Mapping": ["visio"],
    "Project Management": ["pmp"], "Excel": ["ms excel", "advanced excel", "vlookup", "pivot tables"],
    "Data Analysis": ["data analytics"], "Statistics": [], "SAS": [], "SPSS": [], "Alteryx": [],
    "SIEM": [], "SOC": [], "Penetration Testing": ["pen testing", "pentesting"],
    "Vulnerability Management": ["vulnerability assessment"], "Okta": [], "CrowdStrike": [], "Wireshark": [],
    "ISO 27001": [], "NIST": [], "SOX": [],
    "Cisco": [], "CCNA": [], "Routing": [], "Switching": [], "BGP": [], "OSPF": [], "Palo Alto": [], "Fortinet": [], "VPN": [],
    "Hibernate": [], "JPA": [], "HTML": ["html5"], "CSS": ["css3"], "Bootstrap": [], "Redux": [], "Next.js": ["nextjs"],
    "Express": ["express.js", "expressjs"], "Entity Framework": [], "MVC": [],
    "Deep Learning": [], "TensorFlow": [], "PyTorch": [], "Scikit-learn": ["sklearn"], "NLP": ["natural language processing"],
    "Generative AI": ["genai", "llm", "llms", "large language models"], "Computer Vision": [],
    "Android": [], "iOS": [], "Flutter": [], "React Native": [],
})
AMBIGUOUS |= {"excel", "routing", "switching", "lightning", "express", "bootstrap", "statistics", "soc"}

# more technology skills (systems, languages, networking, data, AI, web, security)
SKILLS.update({
    'Linux Kernel': ['kernel development', 'kernel programming', 'linux kernel development'],
    'Kernel Modules': ['kernel module'],
    'eBPF': ['bpf'],
    'Device Drivers': ['device driver', 'linux drivers'],
    'Embedded Systems': ['embedded software', 'embedded development'],
    'Firmware': [],
    'RTOS': ['real-time operating system', 'freertos'],
    'Assembly': ['assembly language', 'x86 assembly'],
    'Operating Systems': ['os internals'],
    'Memory Management': [],
    'Multithreading': ['multi-threading', 'concurrency'],
    'Systems Programming': ['low-level programming'],
    'Compilers': ['compiler'],
    'LLVM': [],
    'CMake': [],
    'Bazel': [],
    'GDB': [],
    'Valgrind': [],
    'Virtual Machines': ['hypervisor', 'hypervisors', 'kvm', 'qemu'],
    'Storage Systems': ['file systems', 'filesystems'],
    'Verilog': [],
    'VHDL': [],
    'FPGA': [],
    'Yocto': [],
    'Perl': [],
    'Groovy': [],
    'Lua': [],
    'Haskell': [],
    'Elixir': [],
    'Erlang': [],
    'Dart': [],
    'Objective-C': [],
    'MATLAB': [],
    'Solidity': [],
    'C Programming': ['ansi c', 'c language', 'c/c++'],
    'HTTP': ['https protocol', 'http/2'],
    'CDN': ['content delivery network'],
    'Cloudflare': [],
    'Load Balancing': [],
    'SD-WAN': ['sdwan'],
    'Network Security': [],
    'gRPC': [],
    'Protocol Buffers': ['protobuf'],
    'WebSockets': ['websocket'],
    'AWS CDK': ['cdk'],
    'Bicep': [],
    'ARM Templates': ['arm template'],
    'Azure Functions': [],
    'Azure AD': ['entra id', 'azure active directory'],
    'Cloud Run': [],
    'Cloud Functions': [],
    'Cosmos DB': ['cosmosdb'],
    'Bigtable': [],
    'Nomad': [],
    'Crossplane': [],
    'Karpenter': [],
    'Kustomize': [],
    'Argo Workflows': [],
    'Backstage': [],
    'Linkerd': [],
    'Envoy': [],
    'HAProxy': [],
    'Cilium': [],
    'Sentry': [],
    'Loki': [],
    'Jaeger': [],
    'Honeycomb': [],
    'Elastic Stack': ['elastic stack'],
    'Sumo Logic': [],
    'Flink': ['apache flink'],
    'Apache Iceberg': ['iceberg'],
    'Trino': ['presto'],
    'Fivetran': [],
    'DAX': [],
    'Power Query': [],
    'SSRS': [],
    'Synapse': ['azure synapse'],
    'Data Factory': ['azure data factory', 'adf'],
    'ClickHouse': [],
    'Neo4j': [],
    'MariaDB': [],
    'SQLite': [],
    'Memcached': [],
    'Pub/Sub': ['pubsub'],
    'Data Governance': [],
    'Data Quality': [],
    'RAG': ['retrieval augmented generation', 'retrieval-augmented generation'],
    'LangChain': [],
    'LlamaIndex': [],
    'Hugging Face': ['huggingface'],
    'Prompt Engineering': [],
    'Vector Databases': ['vector database', 'vector db'],
    'Pinecone': [],
    'SageMaker': ['amazon sagemaker'],
    'Vertex AI': [],
    'Kubeflow': [],
    'MLflow': [],
    'OpenAI API': ['openai'],
    'Keras': [],
    'XGBoost': [],
    'Fine-tuning': ['fine tuning'],
    'Tailwind CSS': ['tailwind'],
    'Svelte': [],
    'Webpack': [],
    'Vite': [],
    'Jest': [],
    'Mocha': [],
    'Storybook': [],
    'SASS': ['scss'],
    'jQuery': [],
    'Laravel': [],
    'Ruby on Rails': ['ruby on rails'],
    'Blazor': [],
    'SwiftUI': [],
    'Jetpack Compose': [],
    'Xcode': [],
    'Android Studio': [],
    'Firebase': [],
    'Unity': ['unity3d'],
    'WebAssembly': ['wasm'],
    'OWASP': [],
    'SAST': [],
    'DAST': [],
    'Burp Suite': [],
    'Zero Trust': [],
    'SSO': ['single sign-on', 'single sign on'],
    'OAuth': ['oauth2', 'oauth 2.0'],
    'SAML': [],
    'Kerberos': [],
    'PKI': [],
    'TLS': ['ssl/tls', 'ssl'],
    'Threat Modeling': ['threat modelling'],
    'GDPR': [],
    'HIPAA': [],
    'PCI DSS': ['pci-dss', 'pci'],
    'SOC 2': ['soc2'],
    'Incident Response': [],
    'Identity and Access Management': [],
    'macOS': [],
    'Active Directory': [],
    'TDD': ['test-driven development', 'test driven development'],
    'OOP': ['object-oriented programming', 'object oriented programming', 'object-oriented design'],
    'Design Patterns': [],
    'System Design': [],
    'Data Structures': [],
    'Algorithms': [],
    'Code Review': ['code reviews'],
})

TECH_NAMES = set(SKILLS)        # everything above is technology; below are business / HR / operations skills

# business, HR, workforce, recruiting, operations, finance and management skills (non-tech profiles)
BUSINESS_SKILLS = {
    # workforce planning and resourcing
    "Workforce Planning": ["strategic workforce planning", "workforce plan", "workforce plans"],
    "Workforce Management": ["wfm"], "Capacity Planning": ["capacity management"],
    "Resource Management": ["resourcing", "resource managers"], "Resource Planning": ["resource allocation"],
    "Demand Planning": ["demand forecasting", "demand management", "demand and supply"],
    "Supply Planning": ["supply forecasting"], "Headcount Planning": ["headcount"],
    "Forecasting": ["forecasts", "forecast"], "Rostering": ["roster", "rosters", "rota", "rotas", "shift patterns"],
    "Scheduling": ["shift scheduling", "workforce scheduling"],
    "Utilisation": ["utilization", "bench management"], "Internal Mobility": ["redeployment", "internal talent marketplace"],
    "Talent Supply Chain": [], "Staffing": ["staffing operations"], "Global Mobility": ["work permits", "immigration"],
    "Workforce Analytics": ["people analytics", "hr analytics"], "KPI Reporting": ["kpis", "kpi", "key performance indicators"],
    "Management Information": ["mi reporting", "mi reports"], "Dashboards": ["scorecards", "dashboard"],
    # recruiting
    "Recruitment": ["recruiting", "talent acquisition"], "End-to-End Recruitment": ["full cycle recruitment", "full-cycle recruitment", "360 recruitment", "360 recruiter"],
    "Candidate Sourcing": ["sourcing", "headhunting", "talent sourcing"], "Business Development": ["new business", "lead generation"],
    "Account Management": ["client management", "client relationships", "key accounts"], "Billings": ["billing targets", "fee targets"],
    "Sales": ["sales targets", "revenue targets"], "Applicant Tracking System": ["ats", "bullhorn", "greenhouse"],
    "Employer Branding": [], "Interviewing": ["competency-based interviews", "interviews"], "Onboarding": ["induction"],
    "Vendor Management": ["supplier management", "msp", "rpo"], "Contract Management": [],
    # HR
    "HR Business Partnering": ["hrbp", "hr business partner", "business partnering"], "Employee Relations": ["er casework", "er cases"],
    "Employment Law": ["uk employment law", "tupe"], "Performance Management": [], "Talent Management": ["succession planning"],
    "Learning and Development": ["l&d", "training and development"], "Compensation and Benefits": ["reward", "c&b", "benefits"],
    "Payroll": [], "HR Policies": ["policy development", "hr policy"], "Organisational Design": ["organizational design", "org design"],
    "Change Management": ["organisational change", "organizational change", "transformation"],
    "Absence Management": ["sickness absence"], "Disciplinary and Grievance": ["grievance", "disciplinary"],
    "Employee Engagement": [], "Diversity and Inclusion": ["dei", "equality diversity and inclusion", "ed&i"],
    "CIPD": [], "HRIS": ["hr systems", "hr system", "human resources information system"],
    "Workday": [], "SuccessFactors": ["sap successfactors"], "PeopleSoft": ["peoplesoft hcm"], "Oracle HCM": [],
    "BambooHR": [], "Cornerstone": [],
    # operations / management
    "Stakeholder Engagement": ["stakeholder relationships", "stakeholders"], "Team Leadership": ["people management", "line management", "team management", "managing a team"],
    "Coaching": ["mentoring"], "Budget Management": ["budgets", "budgeting", "p&l"], "Process Improvement": ["continuous improvement", "lean", "six sigma"],
    "Operations Management": [], "Service Delivery": [], "SLA Management": ["slas", "service level agreements"],
    "Compliance": ["regulatory compliance", "audit"], "Risk Management": [], "Health and Safety": ["h&s", "iosh", "nebosh"],
    "Working Time Regulations": ["working time directive"], "Union Consultation": ["trade unions", "collective bargaining"],
    "Microsoft Office": ["ms office", "office 365", "microsoft 365"], "Data-Driven Decisions": ["data-driven"],
    "PRINCE2": [], "Programme Management": ["program management"], "Customer Service": [], "Contact Centre": ["call centre", "contact center", "call center"],
}
SKILLS.update(BUSINESS_SKILLS)
AMBIGUOUS |= {"forecast", "roster", "reward", "benefits", "sales", "interviews", "audit", "induction", "stakeholders",
              "headcount", "resourcing", "transformation", "lean", "budgets", "dashboard", "staffing", "immigration",
              "kpi", "msp", "ats", "greenhouse", "bullhorn"}
# tech words that mean something else in a business JD ("networking" = meeting people, "pipeline" = candidates)
TECH_WORDY = {"Networking", "Docker", "Bash", "Observability", "ELB", "Security", "High Availability", "Git", "Oracle",
              "REST API", "SRE", "Machine Learning", "Statistics", "Routing", "Switching", "Lightning", "Express"}

TECH_WORDY |= {"Assembly", "Fine-tuning", "Memory Management", "Storage Systems", "Data Quality", "Data Governance",
               "Incident Response", "Algorithms", "Firmware", "Compilers", "Operating Systems", "Virtual Machines",
               "Load Balancing", "Design Patterns", "Code Review", "System Design", "Data Structures", "Firewalls",
               "Envoy", "Nomad", "Backstage", "Sentry", "Loki", "Honeycomb", "Pinecone", "Jest", "Mocha", "Dart", "Vite",
               "Unity", "Synapse", "Spring", "Kerberos", "Bigtable", "Prompt Engineering", "Threat Modeling", "HTTP", "Lua"}

# soft words that are not real skills even if they appear in a resume's skills list
SOFT = {"communication", "communication skills", "teamwork", "team player", "leadership", "problem solving",
        "time management", "hard working", "adaptability", "collaboration", "critical thinking", "english",
        "hindi", "telugu", "tamil", "attention to detail", "self motivated", "multitasking", "creativity"}


def _pattern(term):
    t = re.escape(term.lower()).replace(r"\ ", r"[\s-]?")
    return re.compile(r"(?<![a-z0-9+#])" + t + r"(?![a-z0-9+#])")


def _needle(term):
    """The longest plain piece of a skill name: if it isn't in the text, the skill can't be either (fast check)."""
    parts = re.split(r"[\s-]+", term.lower())
    return max(parts, key=len) if parts else term.lower()


_PATTERNS = {name: [(_needle(a), _pattern(a)) for a in [name] + alts] for name, alts in SKILLS.items()}
_STRICT = {name: [(_needle(a), _pattern(a)) for a in [name] + alts if a.lower() not in AMBIGUOUS] for name, alts in SKILLS.items()}


_KNOWN = {a.lower() for name, alts in SKILLS.items() for a in [name] + alts}

SECTION_END = re.compile(r"^(professional |work )?(experience|employment|education|projects?|certifications?|"
                         r"summary|profile|achievements|awards|languages|interests|declaration|personal)\b", re.I)


GEO_WORDS = {"uk", "us", "usa", "eu", "emea", "apac", "amer", "latam", "india", "europe", "central europe", "asia",
             "london", "global", "international", "remote", "onsite", "hybrid", "north america", "middle east",
             "united kingdom", "united states", "germany", "france", "ireland", "canada", "australia", "singapore", "uae"}
GENERIC_WORDS = {"demand", "delivery", "planning", "reporting", "learning", "analytics", "operations", "development",
                 "leadership", "management", "strategy", "business", "people", "teams", "team", "clients", "client",
                 "data", "process", "processes", "domain", "projects", "project", "support", "service", "services",
                 "visa", "visas", "travel", "office", "experience", "knowledge", "work", "role", "roles"}
_ADJ = {"advanced", "intermediate", "beginner", "expert", "proficient", "fluent", "native", "reduction", "capacity",
        "improvement", "excellence", "awareness", "exposure", "familiarity", "practices", "decisions"}
_SKIP_SKILL_LINES = re.compile(r"^(languages?|awards?|honou?rs|interests|hobbies|references|domain|industries)\b", re.I)


def learn_skills(resume_text):
    return list(_learn_skills(resume_text or ""))


@functools.lru_cache(maxsize=64)
def _learn_skills(resume_text):
    """Skills written in the resume's own Skills section, e.g. 'Tools: Jira, Zephyr, qTest'.
    Lets every profile be scored on its own skills, whatever the role."""
    out, inside = [], False
    for line in (resume_text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^(technical |core |key )?(skills|competencies|tools|technologies|tech stack)\b", s, re.I):
            inside = True
            s = re.sub(r"^[^:]*skills[^:]*:?|^[^:]*(competencies|tools|technologies|tech stack)[^:]*:?", "", s, flags=re.I)
        elif inside and SECTION_END.match(s) and len(s) < 40 and ":" not in s:
            inside = False
        if not inside or _SKIP_SKILL_LINES.match(s):
            continue
        if ":" in s:                       # "Cloud: AWS, Azure" -> "AWS, Azure"
            s = s.split(":", 1)[1]
        s = re.sub(r"[()\[\]{}]", ",", s)   # "AWS (EC2, S3)" -> "AWS, EC2, S3"
        for item in re.split(r"[,;|•●▪·]|\s{2,}|\band\b", s):
            item = re.sub(r"\(.*?\)", "", item).strip(" .-–")
            low = item.lower()
            if 2 <= len(item) <= 30 and len(item.split()) <= 3 and not low.isdigit() and not re.match(r"\d", low) \
                    and low not in SOFT and low not in _KNOWN and low not in GEO_WORDS and low not in GENERIC_WORDS \
                    and not (" " not in item and item.islower() and (len(item) < 9 or low in _ADJ)) \
                    and re.search(r"[a-z]", low):
                out.append(item)
    return tuple(sorted(set(out), key=str.lower))


def find_skills(text, strict=False, extra=()):
    """{skill: how many times it appears}"""
    low = (text or "").lower()
    found = {}
    for name, pats in (_STRICT if strict else _PATTERNS).items():
        n = sum(len(p.findall(low)) for needle, p in pats if needle in low)
        if n:
            found[name] = n
    for name in extra:                     # the profile's own skills
        n = len(_pattern(name).findall(low))
        if n:
            found[name] = n
    return found


def score(jd, resume_text, title="", roles=()):
    """Returns (percent_int, matched_list, missing_list).
    Skills part: how many of the JD's hard-skill keywords (dictionary skills + common ATS phrases + tool names in
    the requirements) the resume has. With a job title it also checks the job's function: 75% skills + 25% title
    (the same keywords appear in very different jobs, e.g. 'recruitment' for a recruiter and for a workforce planner)."""
    if not (jd or "").strip() or not (resume_text or "").strip():
        return 0, [], []
    hard = [k for k in jd_keywords(jd, resume_text) if k[3] == "hard"]
    if not hard:
        pct, matched, missing = _dictionary_score(jd, resume_text)
    else:
        matched_k = [k for k in hard if has_keyword(resume_text, k[0], k[1])]
        pct = round(100 * sum(k[2] for k in matched_k) / max(1, sum(k[2] for k in hard)))
        if len(hard) < 4:                                   # too few keywords to be sure: don't promise 100%
            pct = min(pct, 60 + 10 * len(hard))
        matched, missing = [k[0] for k in matched_k], [k[0] for k in hard if k not in matched_k]
    if title:
        pct = round(0.75 * pct + 0.25 * title_score(title, resume_text, roles))
    return pct, matched, missing


def title_score(title, resume_text, roles=()):
    return _title_score(title or "", resume_text or "", tuple(roles or ()))


@functools.lru_cache(maxsize=20000)
def _title_score(title, resume_text, roles=()):
    """0-100: how close the job title is to the candidate's roles (target roles, resume headline, past job titles)."""
    if title_fit(title, roles):
        return 100
    t = set(_title_words(title)) - {"manager", "engineer", "specialist", "executive", "officer", "consultant",
                                    "analyst", "partner", "advisor", "coordinator", "assistant", "director"}
    if not t:
        return 50
    text = resume_text or ""
    cut = re.search(r"\n\s*(summary|profile|professional summary|career summary|objective)\s*\n", text, re.I)
    head = text[:min(cut.start() if cut else 300, 300)]          # name + headline only, not the summary
    own = set(_title_words(" ".join(roles or ()) + " " + head))
    for line in (resume_text or "").splitlines():            # past job titles: lines with dates
        if re.search(r"(19|20)\d{2}\s*[–—-]", line) or re.search(r"[—–|].*(manager|executive|engineer|lead|analyst)", line, re.I):
            own |= set(_title_words(line))
    return round(100 * len(t & own) / len(t))


def _dictionary_score(jd, resume_text):
    """The older score: only skills from the dictionary."""
    if not (jd or "").strip() or not (resume_text or "").strip():
        return 0, [], []
    extra = learn_skills(resume_text)
    in_jd = find_skills(jd, strict=True, extra=extra)   # be careful what we call a JD requirement
    if not in_jd:
        return 0, [], []
    in_resume = find_skills(resume_text, extra=extra)   # be generous with what the resume shows
    weight = {s: min(n, 3) for s, n in in_jd.items()}
    matched = [s for s in weight if s in in_resume]
    missing = [s for s in weight if s not in in_resume]
    pct = round(100 * sum(weight[s] for s in matched) / max(1, sum(weight.values())))
    by_weight = lambda s: (-weight[s], s.lower())
    return pct, sorted(matched, key=by_weight), sorted(missing, key=by_weight)


# ---------------------------------------------------------------- does the job title fit the profile?
LEVEL_WORDS = {"senior", "sr", "junior", "jr", "lead", "principal", "staff", "associate", "chief", "head",
               "i", "ii", "iii", "iv", "1", "2", "3", "level", "entry", "mid", "remote", "hybrid", "contract",
               "the", "of", "and", "for", "a", "an", "to", "-", "/", "&"}


@functools.lru_cache(maxsize=20000)
def _title_words(text):
    """Job title -> list of plain words, in order, without level words. 'Sr. Dev Ops Engineers' -> ['devops','engineer']"""
    t = (text or "").lower()
    t = re.sub(r"\(.*?\)", " ", t)                                    # "(m/w/d)", "(Remote)"
    t = re.sub(r"\bdev\s*-?\s*ops\b", "devops", t)
    t = re.sub(r"\bsre\b", "site reliability engineer", t)
    t = re.sub(r"\bsec\s*ops\b", "secops", t)
    words = re.sub(r"[^a-z0-9+#.]+", " ", t).split()
    swaps = {"engineers": "engineer", "engineering": "engineer", "engg": "engineer", "eng": "engineer",
             "developers": "developer", "dev": "developer", "administrators": "administrator", "admin": "administrator",
             "analysts": "analyst", "sr.": "senior", "devsecops": "devsecops"}
    return tuple(swaps.get(w, w) for w in words if w not in LEVEL_WORDS and swaps.get(w, w) not in LEVEL_WORDS)


def _contains(seq, sub):
    return any(seq[i:i + len(sub)] == sub for i in range(len(seq) - len(sub) + 1))


# a title with one of these words always fits a DevOps-type role list
CORE_WORDS = {"devops": "DevOps Engineer", "devsecops": "DevSecOps Engineer", "kubernetes": "Kubernetes Engineer"}


def title_fit(title, roles):
    return _title_fit(title or "", tuple(roles or ()))


@functools.lru_cache(maxsize=20000)
def _title_fit(title, roles):
    """Which of the target roles this job title fits, or None.
    The role words must appear together in the title: 'Senior Cloud / DevOps Engineer' fits 'DevOps Engineer',
    but 'Senior Data Engineer - Data Platform' does NOT fit 'Platform Engineer'."""
    t = _title_words(title)
    for role in roles or []:
        r = _title_words(role)
        if r and _contains(t, r):
            return role
    role_words = {w for role in roles or [] for w in _title_words(role)}
    for w, label in CORE_WORDS.items():
        if w in t and w in role_words:
            return label
    return None


# ---------------------------------------------------------------- roles read from a resume
COMMON_TITLES = [
    "DevOps Engineer", "Site Reliability Engineer", "SRE", "Platform Engineer", "Cloud Engineer", "Cloud Architect",
    "Infrastructure Engineer", "Build and Release Engineer", "Release Engineer", "Kubernetes Engineer",
    "Data Engineer", "Data Analyst", "Data Scientist", "Machine Learning Engineer", "ML Engineer", "AI Engineer",
    "ETL Developer", "BI Developer", "Business Intelligence Analyst", "Database Administrator",
    "Software Engineer", "Software Developer", "Full Stack Developer", "Full Stack Engineer", "Java Developer",
    "Python Developer", ".NET Developer", "Frontend Developer", "Front End Developer", "Backend Developer",
    "Back End Developer", "Mobile Developer", "Android Developer", "iOS Developer", "React Developer",
    "QA Engineer", "QA Analyst", "Test Engineer", "Automation Test Engineer", "Test Automation Engineer", "SDET",
    "Business Analyst", "Project Manager", "Scrum Master", "Product Manager", "Product Owner",
    "Salesforce Developer", "Salesforce Administrator", "SAP Consultant", "Network Engineer", "Security Engineer",
    "Cybersecurity Analyst", "Security Analyst", "Systems Administrator", "System Administrator", "Linux Administrator",
]


def guess_roles(resume_text):
    """Job titles written in the resume (used when a profile has no target roles)."""
    low = (resume_text or "").lower()
    found = []
    for t in COMMON_TITLES:
        if _pattern(t).search(low) and t not in found:
            found.append(t)
    return found[:6]


# ---------------------------------------------------------------- which jobs fit this resume? (no typing needed)
# If a resume has enough skills of a family, the family's roles are searched.
ROLE_FAMILIES = [
    ({"Kubernetes", "Docker", "Terraform", "Jenkins", "AWS", "Azure", "GCP", "Ansible", "Helm", "CI/CD", "GitHub Actions",
      "GitLab CI", "Prometheus", "Grafana", "Linux", "CloudFormation", "ArgoCD", "EKS", "Azure DevOps"},
     ["DevOps Engineer", "Site Reliability Engineer", "Platform Engineer", "Cloud Engineer", "Infrastructure Engineer",
      "Cloud Infrastructure Engineer", "Build and Release Engineer", "Release Engineer", "DevSecOps Engineer",
      "Kubernetes Engineer", "AWS Engineer", "Cloud Operations Engineer", "Production Engineer", "CI/CD Engineer"]),
    ({"Spark", "Airflow", "Snowflake", "Databricks", "dbt", "Kafka", "ETL", "Redshift", "BigQuery", "Hadoop", "Hive",
      "Glue", "Data Warehouse", "Data Lake", "Data Modeling", "Informatica"},
     ["Data Engineer", "Big Data Engineer", "ETL Developer", "Analytics Engineer", "Data Platform Engineer"]),
    ({"Tableau", "Power BI", "Excel", "Looker", "Statistics", "Data Analysis", "SAS", "Alteryx"},
     ["Data Analyst", "Business Intelligence Analyst", "BI Developer", "Reporting Analyst"]),
    ({"Machine Learning", "TensorFlow", "PyTorch", "Scikit-learn", "NLP", "Generative AI", "Deep Learning", "MLOps",
      "Computer Vision"},
     ["Machine Learning Engineer", "Data Scientist", "AI Engineer", "MLOps Engineer"]),
    ({"Selenium", "TestNG", "Cypress", "Playwright", "Appium", "Postman", "JMeter", "Manual Testing", "Automation Testing",
      "API Testing", "Regression Testing", "Cucumber", "JUnit", "Test Cases", "UAT"},
     ["QA Engineer", "QA Analyst", "Test Automation Engineer", "SDET", "Quality Engineer", "Test Engineer"]),
    ({"Java", "Spring Boot", "Hibernate", "JPA", "Microservices", "Maven", "Kafka"},
     ["Java Developer", "Backend Developer", "Software Engineer", "Java Full Stack Developer"]),
    ({"React", "Angular", "Vue", "JavaScript", "TypeScript", "HTML", "CSS", "Redux", "Next.js"},
     ["Frontend Developer", "UI Developer", "React Developer", "Full Stack Developer"]),
    ({"Python", "Django", "Flask", "FastAPI", "REST API", "PostgreSQL"},
     ["Python Developer", "Backend Developer", "Software Engineer"]),
    ({"C#", ".NET", "Entity Framework", "MVC", "SQL Server"},
     [".NET Developer", "C# Developer", "Software Engineer"]),
    ({"Node.js", "Express", "MongoDB", "TypeScript"},
     ["Node.js Developer", "Backend Developer", "Full Stack Developer"]),
    ({"Android", "iOS", "Flutter", "React Native", "Kotlin", "Swift"},
     ["Mobile Developer", "Android Developer", "iOS Developer", "Flutter Developer"]),
    ({"Salesforce", "Apex", "Visualforce", "Lightning", "SOQL", "Sales Cloud", "Service Cloud"},
     ["Salesforce Developer", "Salesforce Administrator", "Salesforce Consultant"]),
    ({"SAP", "ABAP", "SAP FICO", "SAP MM", "SAP SD", "S/4HANA"},
     ["SAP Consultant", "SAP Developer", "SAP Analyst"]),
    ({"Business Analysis", "Requirements Gathering", "User Stories", "Stakeholder Management", "Process Mapping", "Jira",
      "Agile", "UAT"},
     ["Business Analyst", "Business Systems Analyst", "Product Analyst"]),
    ({"Cisco", "CCNA", "Routing", "Switching", "BGP", "OSPF", "Palo Alto", "Fortinet", "VPN", "Networking"},
     ["Network Engineer", "Network Administrator"]),
    ({"SIEM", "SOC", "Penetration Testing", "Vulnerability Management", "Okta", "CrowdStrike", "Splunk", "ISO 27001", "NIST"},
     ["Security Engineer", "Cybersecurity Analyst", "SOC Analyst", "Security Analyst"]),
    ({"MySQL", "PostgreSQL", "Oracle", "SQL Server", "MongoDB", "Redis", "Cassandra"},
     ["Database Administrator", "Database Engineer"]),
]


GENERIC_TITLES = {"Software Engineer", "Software Developer"}


def years_of_experience(resume_text):
    """'DevOps Engineer with 4+ years of experience' -> 4 (None if not written)."""
    head = _WORD_NUM.sub(lambda w: str(_NUMS[w.group(1).lower()]), (resume_text or "")[:1500])   # "Four years" -> 4
    m = re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", head, re.I)
    return max(int(x) for x in m) if m else None


def roles_from_resume(resume_text, limit=14):
    """Roles worth searching for this resume: the main profile (from the summary) and its sub-roles.
    Other skill areas are added only if they are almost as strong as the main one."""
    head = (resume_text or "")[:700]                          # name, headline and summary
    titles = [t for t in guess_roles(head) if t not in GENERIC_TITLES]
    have = set(find_skills(resume_text).keys())
    families = []
    for skills, roles in ROLE_FAMILIES:
        hits = len(skills & have)
        if hits >= 3 or (hits >= 2 and len(skills) <= 6):
            families.append((hits, roles))
    families.sort(key=lambda f: -f[0])
    out = list(titles)
    if families:
        top = families[0][0]
        for hits, roles in families:
            if hits < 0.6 * top:                              # side skills (e.g. a little Java or Selenium): skip
                break
            out += [r for r in roles if r not in out]
    if not out:
        out = guess_roles(resume_text)
    return out[:limit]


# ---------------------------------------------------------------- years of experience a JD asks for
_YEARS = re.compile(r"(?:minimum of|min\.?|at least|over)?\s*(\d{1,2})\s*(?:\+|plus)?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*)?\+?\s*"
                    r"(?:years?|yrs?)\b(?=(.{0,60}))", re.I)
_NUMS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                    "fourteen fifteen".split())}
_WORD_NUM = re.compile(r"\b(" + "|".join(list(_NUMS)[1:]) + r")(?=\s*\+?\s*(?:\(\d+\)\s*)?(?:years?|yrs?)\b)", re.I)
_EXP_CONTEXT = re.compile(r"experience|exp\b|professional|industry|hands-on|working|work in|background|relevant|"
                          r"similar role|in a similar|in the field|in a .{0,25}role|post-qualification|track record|"
                          r"in (?:devops|cloud|software|it|sre|engineering)|of (?:devops|cloud|software|it|sre|engineering)", re.I)
_NOT_EXP = re.compile(r"old|founded|history|in business|anniversary|warranty|award|clearance|citizen|degree", re.I)


def jd_years(jd):
    """Years of experience the JD asks for (the highest minimum it mentions), or None if it doesn't say.
    '5+ years of experience' -> 5, '3-5 years' -> 3, 'minimum of 7 years of IT experience' -> 7."""
    best = None
    jd = _WORD_NUM.sub(lambda w: str(_NUMS[w.group(1).lower()]), jd or "")    # "seven years" -> "7 years"
    for m in _YEARS.finditer(jd or ""):
        low, tail = int(m.group(1)), m.group(3) or ""
        before = re.split(r"[.!?\n]", (jd or "")[max(0, m.start() - 40):m.start()])[-1]   # same sentence only
        if low > 20 or _NOT_EXP.search(tail[:30]) or _NOT_EXP.search(before):
            continue
        if not (_EXP_CONTEXT.search(tail) or _EXP_CONTEXT.search(before)):
            continue
        best = low if best is None else max(best, low)
    for m in re.finditer(r"experience\s*(?:required|level)?\s*[:\-–]\s*(\d{1,2})\s*(?:\+|or above|or more|years?|yrs?)",
                         jd or "", re.I):                    # "EXPERIENCE : 12 OR ABOVE"
        low = int(m.group(1))
        if low <= 20:
            best = low if best is None else max(best, low)
    return best


# ---------------------------------------------------------------- ATS keywords and report
# Phrases ATS tools (Jobscan, Resume Worded ...) commonly pick from tech JDs that are not single tools.
EXTRA_TERMS = [
    "troubleshooting", "scripting", "debugging", "performance tuning", "capacity planning", "scalability",
    "load balancing", "cost optimization", "root cause analysis", "on-call", "incident response", "incident management",
    "change management", "release management", "configuration management", "distributed systems", "system design",
    "data structures", "algorithms", "compliance", "logging", "alerting", "automation", "cloud migration",
    "orchestration", "virtualization", "backup", "unit testing", "integration testing", "code review", "mentoring",
    "documentation", "sdlc", "slos", "slas", "production support", "patching", "linux administration", "cloud security",
    "cost management", "finops", "data pipelines", "caching", "message queues", "event-driven", "blue-green", "canary",
    "rollback", "postmortems", "runbooks", "high availability", "disaster recovery", "infrastructure as code",
    "continuous integration", "continuous delivery", "continuous deployment", "version control", "best practices",
    "security", "networking", "monitoring", "observability", "microservices", "containerization", "deployment",
    "infrastructure", "cloud infrastructure", "reliability", "performance", "testing", "automation testing",
]
_EXTRA_PATTERNS = {t: _pattern(t) for t in EXTRA_TERMS if t not in _KNOWN}
SOFT_TERMS = sorted(SOFT | {"problem-solving", "communication skills", "interpersonal", "stakeholder", "ownership",
                            "mentoring", "self-starter", "fast-paced", "cross-functional", "analytical"})
_SOFT_PATTERNS = {t: _pattern(t) for t in SOFT_TERMS}
_CAPS = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9+#./-]*[A-Z0-9][A-Za-z0-9+#.-]*)(?![A-Za-z0-9])")
_CAPS_STOP = {"US", "USA", "UK", "EEO", "EOE", "LLC", "INC", "LTD", "NJ", "NY", "CA", "TX", "PTO", "HR", "CEO", "CTO",
              "FAQ", "ID", "IT", "OK", "PST", "EST", "CST", "EU", "W2", "C2C", "H1B", "GC", "USC", "OPT", "CPT", "TN",
              "EAD", "DOE", "COVID", "ADA", "VP", "AM", "PM", "II", "III", "IV", "JD", "FTE", "WFH", "ASAP", "AND", "THE"}
_CAPS_STOP |= {"CPU", "USD", "EAR", "ITAR", "DOD", "SOS", "SPA", "H-1B", "H1-B", "TS/SCI", "SCI", "SSN", "DOB", "EOE/AA",
               "AA", "EEOC", "OFCCP", "PAY", "SALARY", "BENEFITS", "REMOTE", "HYBRID", "ONSITE", "NOTE", "URGENT",
               "REQUIRED", "PREFERRED", "MUST", "PLUS", "NICE", "BONUS", "DUTIES", "ROLE", "TEAM", "ABOUT", "JOB", "W-2",
               "1099", "C2H", "CTH", "FT", "PT", "HR", "IST", "PDT", "EDT", "CDT", "MST", "UTC", "GMT", "BS", "MS", "BA",
               "MBA", "PHD", "PH.D", "STEM", "NDA", "LCA", "GCP-EAD", "USA-BASED"}


def _tool_like(tok):
    """Does a capitalised word from a JD look like a tool / technology name (not 'On-Site', 'U.S', 'FOUNDRY', 'E1')?"""
    if "." in tok.strip(".") and not re.search(r"\.(js|net|io)$", tok, re.I):
        return False                                        # U.S, Ph.D (but Node.js / ASP.NET are fine)
    if len(tok) <= 2:
        return False                                        # SE, DC, VA, MA, E1
    if sum(c.isdigit() for c in tok) >= 4 or re.fullmatch(r"[A-Z]\d{1,2}", tok):
        return False                                        # requisition numbers, E1 / E2
    parts = [x for x in re.split(r"[-/]", tok) if x]
    if len(parts) > 1 and any(re.fullmatch(r"[A-Z]?[a-z]{2,}", x) for x in parts):
        return False                                        # On-Site, Model-Driven, Forward-Looking, AI-enabled
    if tok.isalpha() and tok.isupper() and len(tok) >= 6:
        return False                                        # FOUNDRY, AGENTIC: words written in capitals
    if re.fullmatch(r"[A-Z]{2,4}s", tok) and tok[:-1] not in {"API", "SLA", "SLO", "VM", "OS", "CRD", "LLM"}:
        return False                                        # PMs, SMEs, TAMs: people, not tools
    if re.fullmatch(r"(Gen|Ver|Rev|Tier|Level|Phase|Step|Wave)\d+", tok, re.I):
        return False                                        # Gen2, Tier1
    return True


_REQ_LINE = re.compile(r"experience|knowledge|proficien|familiar|skill|required|requirement|preferred|must|nice to have|"
                       r"qualification|hands-on|expert|strong|working with|using|tools?|technolog|stack", re.I)


_NOISE = {"services", "service", "management", "support", "systems", "system", "tools", "platforms", "platform",
          "applications", "solutions", "operations", "process", "processes", "incident", "testing", "engineering",
          "development", "software", "technology", "data", "cloud", "infrastructure", "performance", "security"}


# HR words in a tech JD are about the company (benefits, hiring process), not skills the engineer needs
HR_BOILER = {"compensation and benefits", "onboarding", "recruiting", "recruitment", "diversity and inclusion",
             "work permits", "rpo", "payroll", "interviewing", "employer branding", "talent management",
             "candidate sourcing", "end-to-end recruitment", "people-management", "global mobility", "internal mobility",
             "employee engagement", "employee relations", "learning and development", "absence management",
             "hr policies", "talent acquisition", "benefits", "utilization", "utilisation"}


def is_tech(text):
    """True if the text is about technology work (a few real tech tools, not just 'networking')."""
    low = (text or "").lower()
    hits = {n for n in TECH_NAMES - TECH_WORDY for needle, p in _STRICT.get(n, []) if needle in low and p.search(low)}
    return len(hits) >= 3


BUSINESS_EXTRA = {"capacity planning", "change management", "compliance", "documentation", "mentoring",
                  "best practices", "release management"}


def jd_keywords(jd, resume_text="", company=""):
    """ATS keywords of a JD (cached: the same JD is scored several times during one Collect)."""
    return list(_jd_keywords(jd or "", resume_text or "", company or ""))


@functools.lru_cache(maxsize=4000)
def _jd_keywords(jd, resume_text="", company=""):
    """ATS keywords of a JD, most important first: [(display, key, weight, kind)] with kind 'hard' or 'soft'.
    Uses the skills dictionary, the resume's own Skills list, common ATS phrases and tool names in the requirements."""
    jd = jd or ""
    low = jd.lower()
    extra = learn_skills(resume_text) if resume_text else []
    out, seen = [], set()

    def first_pos(pats):
        pos = [m.start() for p in pats for m in [p.search(low)] if m]
        return min(pos) if pos else 10 ** 6

    def spelled(pats, default):
        for p in pats:
            m = p.search(low)
            if m:
                return re.sub(r"\s+", " ", jd[m.start():m.end()])      # "Azure\nDevOps" -> "Azure DevOps"
        return default

    tech = is_tech(jd)
    items = []
    for name, n in find_skills(jd, strict=True, extra=extra).items():
        if not tech and name in TECH_WORDY:
            continue                     # "networking" in a recruiter JD is not TCP/IP
        if name.lower() in GEO_WORDS or name.lower() in GENERIC_WORDS:
            continue
        pats = [_pattern(a) for a in [name] + SKILLS.get(name, []) if a.lower() not in AMBIGUOUS] or [_pattern(name)]
        items.append((spelled(pats, name), name.lower(), min(n, 3), "hard", first_pos(pats)))
    for t, p in _EXTRA_PATTERNS.items():
        if not tech and t not in BUSINESS_EXTRA:
            continue                     # "automation", "deployment", "testing" … mean other things outside tech
        n = len(p.findall(low))
        if n:
            items.append((spelled([p], t), t, min(n, 3), "hard", first_pos([p])))
    company_words = {w for w in re.split(r"\W+", (company or "").lower()) if w}
    cw = [w for w in re.findall(r"[A-Za-z0-9]+", company or "") if w.lower() not in {"inc", "llc", "ltd", "corp", "co"}]
    company_words |= {"".join(w[0] for w in cw).lower(), "".join(w[0] for w in cw if w[0].isupper()).lower()} - {""}
    for line in (jd.splitlines() or [jd]) if tech else []:     # unknown tool names: only in tech JDs (not "LCY")
        if not _REQ_LINE.search(line):
            continue
        for m in _CAPS.finditer(line):
            tok = m.group(1).strip(".-/")
            up = sum(c.isupper() for c in tok) + sum(c.isdigit() for c in tok)
            if len(tok) < 2 or len(tok) > 20 or up < 2 or tok.upper() in _CAPS_STOP or tok.lower() in company_words:
                continue
            if not _tool_like(tok):
                continue
            if tok.lower() in _KNOWN or any(tok.lower() == i[1] for i in items):
                continue
            items.append((tok, tok.lower(), max(1, min(len(_pattern(tok).findall(low)), 3)), "hard", m.start()))
    for t, p in _SOFT_PATTERNS.items():
        n = len(p.findall(low))
        if n:
            items.append((spelled([p], t), t, 1, "soft", first_pos([p])))
    keys = {i[1] for i in items}
    for disp, key, w, kind, pos in sorted(items, key=lambda i: (i[3] != "hard", -i[2], i[4])):
        if key in seen or key in _NOISE or key in company_words or (company and key in company.lower()) \
                or key in GEO_WORDS or key in GENERIC_WORDS or (tech and key in HR_BOILER):
            continue
        if " " not in key and any(key != k and re.search(r"(?<![a-z])" + re.escape(key) + r"(?![a-z])", k) for k in keys):
            continue                     # "automation" when "automation testing" is there too
        seen.add(key)
        out.append((disp.strip(), key, max(1, w), kind))
    return tuple(out)


def has_keyword(text, display, key):
    """Is this JD keyword in the text (any known spelling)?"""
    low = (text or "").lower()
    pats = [_pattern(display), _pattern(key)]
    for name, alts in SKILLS.items():
        if name.lower() == key:
            pats += [_pattern(a) for a in [name] + alts]
            break
    return any(p.search(low) for p in pats)


DEGREES = [("phd", r"\bph\.?d\b|doctorate"), ("master", r"\bmaster'?s?\b|\bm\.?s\.?\b|\bmba\b|\bm\.?tech\b|\bmca\b"),
           ("bachelor", r"\bbachelor'?s?\b|\bb\.?s\.?\b|\bb\.?e\.?\b|\bb\.?tech\b|\bbca\b|undergraduate degree|\bdegree\b")]


def _degree(text):
    for name, pat in DEGREES:
        if re.search(pat, text or "", re.I):
            return name
    return None


def ats_report(jd, resume_text, job_title="", company=""):
    """ATS-style check of a resume against a JD, like Jobscan: a score out of 100 and what to fix.
    hard skills 55 · job title 15 · soft skills 10 · experience 10 · education 5 · format 5"""
    kws = jd_keywords(jd, resume_text, company)
    hard = [k for k in kws if k[3] == "hard"]
    soft = [k for k in kws if k[3] == "soft"]
    low = (resume_text or "").lower()

    def count(disp, key):
        pats = [_pattern(disp), _pattern(key)] + [_pattern(a) for n, al in SKILLS.items() if n.lower() == key for a in [n] + al]
        return max(len(p.findall(low)) for p in pats)

    got = {k[1]: count(k[0], k[1]) for k in hard}
    # a keyword the JD repeats should be in the resume more than once (skills list + work experience)
    hard_pts = sum(k[2] * min(1.0, got[k[1]] / max(1, min(k[2], 2))) for k in hard)
    hard_pct = round(100 * hard_pts / max(1, sum(k[2] for k in hard))) if hard else 0
    missing = [k[0] for k in hard if not got[k[1]]]
    too_few = [k[0] for k in hard if got[k[1]] and got[k[1]] < min(k[2], 2)]
    soft_pct = round(100 * sum(1 for k in soft if count(k[0], k[1])) / len(soft)) if soft else 100
    soft_missing = [k[0] for k in soft if not count(k[0], k[1])]

    t = re.sub(r"\s*[\(\[|].*$|\s+[-–—]\s+.*$", "", job_title or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    flat = re.sub(r"\s+", " ", low)                          # a title wrapped onto the next line still counts
    core = " ".join(w for w in re.sub(r"[^a-z0-9+#/ ]", " ", t).split() if w not in LEVEL_WORDS)
    flat_words = " ".join(re.sub(r"[^a-z0-9+#/ ]", " ", flat).split())
    title_pct = 100 if t and t in flat else (70 if core and core in flat_words else 0)

    need = jd_years(jd)
    have = years_of_experience(resume_text)
    exp_pct = 100 if need is None or (have is not None and have >= need) else (60 if have and have >= need - 1 else 0)
    want_deg, has_deg = _degree(jd), _degree(resume_text)
    order = {"bachelor": 1, "master": 2, "phd": 3}
    edu_pct = 100 if not want_deg or (has_deg and order[has_deg] >= order[want_deg]) else 0
    fmt = [bool(re.search(r"@", resume_text or "")), bool(re.search(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}|\+\s?\d[\d\s().-]{7,}\d|\b\d{5}\s?\d{5,6}\b", resume_text or "")),
           bool(re.search(r"^\s*(work |professional )?experience\b", resume_text or "", re.I | re.M)),
           bool(re.search(r"^\s*(technical |core )?skills\b", resume_text or "", re.I | re.M)),
           bool(re.search(r"^\s*education\b", resume_text or "", re.I | re.M))]
    fmt_pct = round(100 * sum(fmt) / len(fmt))

    score = round(0.55 * hard_pct + 0.15 * title_pct + 0.10 * soft_pct + 0.10 * exp_pct + 0.05 * edu_pct + 0.05 * fmt_pct)
    tips = []
    if missing:
        tips.append("Add the missing hard skills you really have: " + ", ".join(missing[:10]))
    if too_few:
        tips.append("Mention these again in a work-experience bullet (the JD repeats them): " + ", ".join(too_few[:8]))
    if title_pct < 100 and job_title:
        tips.append(f"Use the job title \"{job_title}\" (or its core words) in the summary")
    if soft_missing:
        tips.append("Soft skills the JD asks for: " + ", ".join(soft_missing[:6]))
    if exp_pct < 100:
        tips.append(f"The JD asks for {need}+ years; the resume shows {have or '?'}")
    if edu_pct < 100:
        tips.append(f"The JD asks for a {want_deg}'s degree")
    return {"score": score, "hard": hard_pct, "title": title_pct, "soft": soft_pct, "experience": exp_pct,
            "education": edu_pct, "format": fmt_pct, "missing": missing, "too_few": too_few,
            "soft_missing": soft_missing, "tips": tips, "keywords": len(hard)}


# ---------------------------------------------------------------- which jobs are most likely to bring a call
def call_chance(job, resume_years=None, roles=(), now=None):
    """0-100: how likely this application is to get a recruiter call, from what recruiters screen on:
    skills match (45%), how fresh the post is (25%: the first applicants get most calls), years asked vs the
    candidate's (20%), and whether the job title is one of the candidate's roles (10%)."""
    from datetime import datetime
    now = now or datetime.now()
    match = job.get("ats_after") or job.get("tailored_match") or job.get("match") or 0
    when = job.get("posted_at") or job.get("saved_at") or ""
    try:
        hours = (now - datetime.fromisoformat(str(when)[:19].replace("T", " "))).total_seconds() / 3600
    except ValueError:
        hours = 24 * 7
    fresh = 100 if hours <= 24 else 85 if hours <= 48 else 65 if hours <= 72 else 45 if hours <= 24 * 7 else 20
    need = jd_years(job.get("jd") or "")
    if need is None or resume_years is None:
        exp = 80
    else:
        gap = need - resume_years
        exp = 100 if gap <= 0 else 75 if gap <= 1 else 35 if gap <= 2 else 10
    fit = 100 if title_fit(job.get("title") or "", roles) else 40
    return round(0.45 * min(match, 100) + 0.25 * fresh + 0.20 * exp + 0.10 * fit)