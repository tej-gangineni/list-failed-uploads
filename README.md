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

## Run it as a query instead (MongoDB Compass)

No script needed: open the `files` collection in Compass and use one of these. Both use the same definition of "failed" as the script: processing not completed and uploaded more than 20 minutes ago, or ARAI marked it failed. Deleted files are excluded.

### Aggregation (with uploader name and email)

**Aggregations** tab, pipeline editor in text mode:

```js
[
  { $match: {
      deleted: { $ne: true },
      $or: [
        { processing_completed: false, uploaded_first_time: { $lt: new Date(Date.now() - 20*60*1000) } },
        { arai_status: "failed" }
      ]
  } },
  { $lookup: {
      from: "users",
      let: { uid: { $toString: "$uploaded_by_user_id" } },
      pipeline: [
        { $match: { $expr: { $eq: [ { $toString: "$_id" }, "$$uid" ] } } },
        { $project: { _id: 0, full_name: 1, email: 1 } }
      ],
      as: "user"
  } },
  { $project: {
      _id: 0,
      filename: 1,
      uploaded_time: "$uploaded_first_time",
      uploaded_by: { $ifNull: [ { $first: "$user.full_name" }, "$uploaded_by_user_id" ] },
      uploaded_by_email: { $first: "$user.email" }
  } },
  { $sort: { uploaded_time: -1 } }
]
```

### Direct find (uploader user id only)

**Documents** tab, click **Options**:

Filter:

```js
{ deleted: { $ne: true }, $or: [ { processing_completed: false, uploaded_first_time: { $lt: new Date(Date.now() - 20*60*1000) } }, { arai_status: "failed" } ] }
```

Project:

```js
{ _id: 0, filename: 1, uploaded_first_time: 1, uploaded_by_user_id: 1 }
```

Sort:

```js
{ uploaded_first_time: -1 }
```

### Only recent uploads

Add this at the top level of the `$match` or Filter, next to `deleted` (example: last 7 days):

```js
uploaded_first_time: { $gte: new Date(Date.now() - 7*24*60*60*1000) },
```

Use **Export Data** in Compass to save the result as CSV.
