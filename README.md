# list-failed-uploads

Read-only script that lists failed file uploads from MongoDB: filename, uploaded time and uploaded by.

## Use

Copy the script into `cpod-core/scripts/` and run it from `cpod-core`:

```bash
git clone https://github.com/tej-gangineni/list-failed-uploads.git
cp list-failed-uploads/list_failed_uploads.py /path/to/cpod-core/scripts/

cd /path/to/cpod-core
python scripts/list_failed_uploads.py                  # all failed uploads, newest first
python scripts/list_failed_uploads.py --since-days 7   # last 7 days only
python scripts/list_failed_uploads.py --csv failed_uploads.csv
```

The Mongo connection is read from `cpod-core/.env` (`DB_URL` and `DB_NAME`). Needs `pymongo` and `python-dotenv`, which the cpod-core environment already has.
