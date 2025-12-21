#!/bin/bash
# Script to help set up and push to GitHub

REPO_NAME="msm"
GITHUB_USER="chughjug"

echo "Setting up GitHub repository..."
echo "Repository name: $REPO_NAME"
echo "GitHub user: $GITHUB_USER"
echo ""

# Check if remote already exists
if git remote get-url origin &>/dev/null; then
    echo "Remote 'origin' already exists:"
    git remote get-url origin
    read -p "Do you want to update it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git remote set-url origin "https://github.com/$GITHUB_USER/$REPO_NAME.git"
    fi
else
    echo "Adding remote origin..."
    git remote add origin "https://github.com/$GITHUB_USER/$REPO_NAME.git"
fi

echo ""
echo "Next steps:"
echo "1. Create the repository on GitHub (if not already created):"
echo "   Go to: https://github.com/new"
echo "   Repository name: $REPO_NAME"
echo "   Make it public or private as you prefer"
echo ""
echo "2. Then run:"
echo "   git push -u origin main"
echo ""
echo "3. After pushing, you can trigger workflows with:"
echo "   python trigger_workflow.py <player_id>"


