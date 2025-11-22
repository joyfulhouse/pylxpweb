#!/bin/bash
# Script to configure branch protection for the main branch
# Run this once to set up protection rules

set -e

REPO="joyfulhouse/pylxpweb"
BRANCH="main"

echo "Setting up branch protection for $REPO/$BRANCH..."

gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "/repos/$REPO/branches/$BRANCH/protection" \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["CI Success"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
EOF

echo ""
echo "✅ Branch protection configured successfully!"
echo ""
echo "Protection rules:"
echo "  ✓ Require pull request before merging (no direct commits to main)"
echo "  ✓ Require 'CI Success' status check to pass"
echo "  ✓ Require branches to be up to date before merging"
echo "  ✓ Dismiss stale PR reviews when new commits are pushed"
echo "  ✓ Enforce rules for administrators"
echo "  ✓ Block force pushes"
echo "  ✓ Block branch deletion"
echo ""
echo "View settings: https://github.com/$REPO/settings/branches"
