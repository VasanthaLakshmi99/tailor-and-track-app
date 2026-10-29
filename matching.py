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
VERSION = "2026-10-30a"   # all Tailor&Track files must have the same version
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

# soft words that are not real skills even if they appear in a resume's skills list
SOFT = {"communication", "communication skills", "teamwork", "team player", "leadership", "problem solving",
        "time management", "hard working", "adaptability", "collaboration", "critical thinking", "english",
        "hindi", "telugu", "tamil", "attention to detail", "self motivated", "multitasking", "creativity"}


def _pattern(term):
    t = re.escape(term.lower()).replace(r"\ ", r"[\s-]?")
    return re.compile(r"(?<![a-z0-9+#])" + t + r"(?![a-z0-9+#])")


_PATTERNS = {name: [_pattern(a) for a in [name] + alts] for name, alts in SKILLS.items()}
_STRICT = {name: [_pattern(a) for a in [name] + alts if a.lower() not in AMBIGUOUS] for name, alts in SKILLS.items()}


_KNOWN = {a.lower() for name, alts in SKILLS.items() for a in [name] + alts}

SECTION_END = re.compile(r"^(professional |work )?(experience|employment|education|projects?|certifications?|"
                         r"summary|profile|achievements|awards|languages|interests|declaration|personal)\b", re.I)


def learn_skills(resume_text):
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
        if not inside:
            continue
        if ":" in s:                       # "Cloud: AWS, Azure" -> "AWS, Azure"
            s = s.split(":", 1)[1]
        s = re.sub(r"[()\[\]{}]", ",", s)   # "AWS (EC2, S3)" -> "AWS, EC2, S3"
        for item in re.split(r"[,;|•●▪·]|\s{2,}|\band\b", s):
            item = re.sub(r"\(.*?\)", "", item).strip(" .-–")
            low = item.lower()
            if 2 <= len(item) <= 30 and len(item.split()) <= 3 and not low.isdigit() \
                    and low not in SOFT and low not in _KNOWN and re.search(r"[a-z]", low):
                out.append(item)
    return sorted(set(out), key=str.lower)


def find_skills(text, strict=False, extra=()):
    """{skill: how many times it appears}"""
    low = (text or "").lower()
    found = {}
    for name, pats in (_STRICT if strict else _PATTERNS).items():
        n = sum(len(p.findall(low)) for p in pats)
        if n:
            found[name] = n
    for name in extra:                     # the profile's own skills
        n = len(_pattern(name).findall(low))
        if n:
            found[name] = n
    return found


def score(jd, resume_text):
    """Returns (percent_int, matched_list, missing_list)."""
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
    pct = round(100 * sum(weight[s] for s in matched) / sum(weight.values()))
    by_weight = lambda s: (-weight[s], s.lower())
    return pct, sorted(matched, key=by_weight), sorted(missing, key=by_weight)


# ---------------------------------------------------------------- does the job title fit the profile?
LEVEL_WORDS = {"senior", "sr", "junior", "jr", "lead", "principal", "staff", "associate", "chief", "head",
               "i", "ii", "iii", "iv", "1", "2", "3", "level", "entry", "mid", "remote", "hybrid", "contract",
               "the", "of", "and", "for", "a", "an", "to", "-", "/", "&"}


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
    return [swaps.get(w, w) for w in words if w not in LEVEL_WORDS and swaps.get(w, w) not in LEVEL_WORDS]


def _contains(seq, sub):
    return any(seq[i:i + len(sub)] == sub for i in range(len(seq) - len(sub) + 1))


# a title with one of these words always fits a DevOps-type role list
CORE_WORDS = {"devops": "DevOps Engineer", "devsecops": "DevSecOps Engineer", "kubernetes": "Kubernetes Engineer"}


def title_fit(title, roles):
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
    m = re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", (resume_text or "")[:1500], re.I)
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