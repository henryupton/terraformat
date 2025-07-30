#!/bin/bash

check_command() {
  if ! command -v "$1" &> /dev/null; then
    echo "Error: Required command '$1' is not installed or not in your PATH."
    exit 1
  fi
}

echo "Checking for dependencies..."
check_command "python3"
check_command "pip"
check_command "twine"

# --- 1. Get the new version from the command-line argument ---
if [[ -z "$1" ]]; then
  echo "Error: No version number provided."
  echo "Usage: ./deploy.sh <version>"
#  exit 1
fi

VERSION=$1

# --- 2. Update version in files ---
echo "Updating version to $VERSION..."
# For macOS (uses -i '' to avoid creating a backup file)
sed -i '' "s/version=\".*\"/version=\"$VERSION\"/" setup.py

# For Linux (GNU sed), the command would be:
# sed -i "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" terraformat/__init__.py
# sed -i "s/version='.*'/version='$VERSION'/" setup.py


# --- 3. Build the package ---
echo "Building the package..."
rm -rf dist/
python3 -m build


# --- 4. Upload to PyPI ---
echo "Uploading to PyPI..."
twine upload dist/*


# --- 5. Commit and tag in Git ---
echo "Committing and tagging version in Git..."
git add setup.py
git commit -m "Bump version to $VERSION"
git tag "v$VERSION"
git push && git push --tags

echo "🚀 Deployment of version $VERSION complete!"