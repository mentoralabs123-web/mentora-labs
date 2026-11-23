"""One-time seed data for the projects database.

This is the ONLY place the original nine projects are written down. It is
used by ``project_schema.seed_projects`` to migrate them into the database
the first time the app starts; after that the database is the source of
truth and this file is never read at request time.

Everything here was carried over from the former ``TRACKS`` list in
``app.py`` (title, short description, technologies, domain tag, learning
group) and from the category assignment made in Task 3A. Nothing was added:
the original data had no long descriptions, problem statements, objectives,
implementation notes, images or links, so those stay empty (None).
"""

# Categories available for assignment. Public filter buttons only appear for
# categories that have at least one published project, so unused ones stay
# hidden. ``art_kind`` picks the fallback artwork for cards without an image
# (one of: ml, dl, data, web).
CATEGORIES = [
    {"slug": "artificial-intelligence", "name": "Artificial Intelligence", "art_kind": "ml"},
    {"slug": "machine-learning", "name": "Machine Learning", "art_kind": "ml"},
    {"slug": "deep-learning", "name": "Deep Learning", "art_kind": "dl"},
    {"slug": "data-science", "name": "Data Science", "art_kind": "data"},
    {"slug": "full-stack-applications", "name": "Full-Stack Applications", "art_kind": "web"},
    {"slug": "web-development", "name": "Web Development", "art_kind": "web"},
    {"slug": "software-applications", "name": "Software Applications", "art_kind": "web"},
]

# Slugs equal the old track keys so existing deep links (#project-nids) keep
# working. The first category listed is the project's primary category.
# display_order is spaced by 10 so new projects can be slotted in between.
PROJECTS = [
    {
        "slug": "nids", "title": "NIDS — Network Intrusion Detection",
        "short_description": "A GAN-based system that flags malicious traffic on 5G networks.",
        "technologies": ["Python", "TensorFlow", "GANs"],
        "domain_tag": "Security · ML", "learning_group": "ml",
        "categories": ["deep-learning", "machine-learning"], "display_order": 10,
    },
    {
        "slug": "skin", "title": "Skin Disease Classification",
        "short_description": "An image classifier that identifies common skin conditions from photos.",
        "technologies": ["Python", "CNN", "Flask"],
        "domain_tag": "Healthcare · CV", "learning_group": "ml",
        "categories": ["deep-learning", "machine-learning"], "display_order": 20,
    },
    {
        "slug": "expense", "title": "Expense Tracker",
        "short_description": "A budgeting app with spend categories, monthly summaries, and charts.",
        "technologies": ["Flask", "HTML/CSS", "SQL"],
        "domain_tag": "Full stack", "learning_group": "fullstack",
        "categories": ["full-stack-applications", "web-development"], "display_order": 30,
    },
    {
        "slug": "heart", "title": "Heart Disease Prediction",
        "short_description": "A machine learning model that predicts heart disease risk from patient health data.",
        "technologies": ["Python", "Machine Learning", "Healthcare"],
        "domain_tag": "Healthcare · ML", "learning_group": "ml",
        "categories": ["machine-learning", "data-science"], "display_order": 40,
    },
    {
        "slug": "house", "title": "House Price Prediction",
        "short_description": "A regression model that estimates house prices from property features.",
        "technologies": ["Python", "Regression", "Pandas"],
        "domain_tag": "Regression · ML", "learning_group": "data",
        "categories": ["machine-learning", "data-science"], "display_order": 50,
    },
    {
        "slug": "flight", "title": "Flight Fare Prediction",
        "short_description": "A regression model that estimates flight ticket prices using route, date, and airline data.",
        "technologies": ["Python", "Regression", "Pandas"],
        "domain_tag": "Regression · ML", "learning_group": "data",
        "categories": ["machine-learning", "data-science"], "display_order": 60,
    },
    {
        "slug": "rice-leaf", "title": "Rice Leaf Disease Prediction",
        "short_description": "A CNN image classifier that identifies diseases in rice leaf photos.",
        "technologies": ["Python", "CNN", "Computer Vision"],
        "domain_tag": "Agriculture · CNN", "learning_group": "ml",
        "categories": ["deep-learning", "machine-learning"], "display_order": 70,
    },
    {
        "slug": "task-manager", "title": "Task Manager",
        "short_description": "An app for creating, assigning, and tracking tasks.",
        "technologies": ["Flask", "Task Tracking", "SQL"],
        "domain_tag": "App", "learning_group": "fullstack",
        "categories": ["full-stack-applications", "web-development"], "display_order": 80,
    },
    {
        "slug": "quiz", "title": "Quiz App",
        "short_description": "An app for building and taking timed multiple-choice quizzes.",
        "technologies": ["Flask", "Quizzes", "JavaScript"],
        "domain_tag": "App", "learning_group": "fullstack",
        "categories": ["full-stack-applications", "web-development"], "display_order": 90,
    },
]
