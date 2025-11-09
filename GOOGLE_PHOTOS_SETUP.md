# Google Photos Integration Setup

## Quick Start

1. **Install dependencies:**
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

2. **See setup instructions:**
```bash
python photocleaner.py --google-photos-setup
```

3. **Follow the steps to:**
   - Create a Google Cloud project
   - Enable Google Photos API
   - Create OAuth 2.0 credentials
   - Download credentials JSON file

4. **Use it:**
```bash
# Preview all photos
python photocleaner.py --google-photos

# Specific album
python photocleaner.py --google-photos --google-photos-album "Camera"

# With date filtering
python photocleaner.py --google-photos --date-from 2025-01-01 --date-to 2025-12-31
```

## Important Notes

- Google Photos API has **read-only** access for most operations
- Photos will be downloaded temporarily for analysis
- Deletion is **identification only** - you'll need to manually delete from Google Photos
- First run will open browser for authentication
- Credentials are cached for future use

## See Also

- Full documentation in README.md
- Dropbox integration for automated deletion
