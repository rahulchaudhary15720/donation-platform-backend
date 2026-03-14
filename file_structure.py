import os

structure = {
    "app": {
        "main.py": "",
        "core": {
            "config.py": "",
            "security.py": "",
            "roles.py": ""
        },
        "db": {
            "base.py": "",
            "session.py": "",
            "init_db.py": ""
        },
        "models": {
            "user.py": "",
            "ngo.py": "",
            "campaign.py": "",
            "milestone.py": "",
            "donation.py": "",
            "email_notification.py": "",
            "proof.py": ""
        },
        "routes": {
            "auth.py": "",
            "ngos.py": "",
            "campaigns.py": "",
            "milestones.py": "",
            "donations.py": "",
            "admin.py": ""
        },
        "utils": {
            "cloudinary.py": "",
            "email_crypto.py": "",
            "email_service.py": ""
        },
        "tasks": {
            "cleanup.py": ""
        }
    }
}

def create_structure(base_path, tree):
    for name, content in tree.items():
        path = os.path.join(base_path, name)
        if isinstance(content, dict):
            os.makedirs(path, exist_ok=True)
            create_structure(path, content)
        else:
            with open(path, "w") as f:
                f.write(content)

if __name__ == "__main__":
    create_structure(".", structure)
    print("✅ App folder structure created successfully")
