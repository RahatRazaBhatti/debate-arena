SOURCE: Stanford University (published at ACM CCS 2023)
TITLE: Do Users Write More Insecure Code with AI Assistants?
AUTHOR/ORGANIZATION: Neil Perry, Megha Srivastava, Deepak Kumar, Dan Boneh (Stanford University)
DATE: 2023 (arXiv preprint 2022; ACM CCS 2023)
URL: https://arxiv.org/abs/2211.03622
TOPIC: AI coding errors, software security, accountability

CONTENT:
Stanford researchers ran the first large-scale user study examining how
developers write code with the help of an AI coding assistant on
security-relevant programming tasks. 47 participants completed five
security-related programming exercises across Python, JavaScript, and C;
33 had access to an AI code assistant and 14 worked without one.

Participants who used the AI assistant wrote meaningfully less secure
code than those who did not, across most of the tasks tested. More
strikingly, participants who used the AI assistant were also more
likely to believe their code was secure than participants who worked
without it -- meaning the tool didn't just introduce vulnerabilities,
it also made users more confident (sometimes wrongly) that their code
was safe. The researchers found that participants who trusted the AI
less, and who engaged more critically with how they phrased their
prompts, tended to produce code with fewer vulnerabilities.

The authors frame this as an argument for pairing AI code assistants
with better security tooling and user education rather than treating
AI output as inherently trustworthy, and recommend filtering insecure
patterns out of the data used to train coding models.

RELEVANCE: Supports the case that unsupervised AI-generated code carries
real security and reliability risks, and that human review and
accountability remain necessary safeguards (AI-limitations /
human-oversight evidence).
