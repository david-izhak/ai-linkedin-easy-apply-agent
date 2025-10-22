# Migration Guide: Job Search Period Configuration Update

## Overview

This guide helps you migrate from the old dynamic job search period calculation to the new fixed `JOB_SEARCH_PERIOD_SECONDS` configuration parameter.

## What Changed?

### Before (Old Approach)
- The bot calculated the search period dynamically based on the last run timestamp
- Used `DEFAULT_JOB_POSTED_FILTER_SECONDS` as a fallback for the first run
- Period varied depending on when the bot was last executed

### After (New Approach)
- Fixed search period configured via `JOB_SEARCH_PERIOD_SECONDS`
- Same period used for every run, regardless of when the bot was last executed
- More predictable and easier to understand behavior

## Breaking Changes

### Configuration Parameter
- **New parameter:** `JOB_SEARCH_PERIOD_SECONDS = 1728000` (20 days by default)
- **Deprecated parameter:** `DEFAULT_JOB_POSTED_FILTER_SECONDS` (kept for backward compatibility)

### Database
- **No breaking changes** - the `run_history` table is preserved
- All existing data remains intact and compatible

### Code Interface
- **No breaking changes** - function signatures remain the same
- Internal implementation simplified (transparent to users)

## Migration Steps

### For Existing Users

#### Step 1: Backup (Optional but Recommended)

```bash
# Backup your current config
cp config.py config.py.backup

# Backup your database
cp jobs.db jobs.db.backup
```

#### Step 2: Update config.py

**Option A: Use the new parameter (Recommended)**

Add the following to your `config.py` around line 32:

```python
# JOB SEARCH TIME PERIOD
# Specifies how far back (in seconds) to search for job postings on LinkedIn.
# This is a fixed period that remains constant regardless of when the bot was last run.
#
# CONVERSION TABLE:
#   1 day    = 86400 seconds
#   7 days   = 604800 seconds
#   14 days  = 1209600 seconds
#   20 days  = 1728000 seconds (default)
#   30 days  = 2592000 seconds
#
# RECOMMENDATIONS:
#   - Daily runs: 1-2 days (86400-172800)
#   - Weekly runs: 7-10 days (604800-864000)
#   - Bi-weekly runs: 14-20 days (1209600-1728000)
#   - Monthly runs: 30 days (2592000)
#
# NOTE: LinkedIn typically shows job postings up to 30-60 days old.
# Using periods longer than 90 days may result in fewer results.
JOB_SEARCH_PERIOD_SECONDS = 1728000  # Default: 20 days
```

**Option B: Keep using the old parameter (Not recommended)**

If you don't update your config, the bot will:
1. Show a deprecation warning
2. Use the value from `DEFAULT_JOB_POSTED_FILTER_SECONDS`
3. Continue to work normally

You can keep using this temporarily, but please migrate to the new parameter when possible.

#### Step 3: Choose Your Search Period

Consider your use case when choosing the period:

| Use Case | Recommended Period | Seconds | Configuration |
|----------|-------------------|---------|---------------|
| Daily runs | 1-2 days | 86400-172800 | `JOB_SEARCH_PERIOD_SECONDS = 172800` |
| Every 3 days | 3-5 days | 259200-432000 | `JOB_SEARCH_PERIOD_SECONDS = 432000` |
| Weekly runs | 7-10 days | 604800-864000 | `JOB_SEARCH_PERIOD_SECONDS = 864000` |
| Bi-weekly runs | 14-20 days | 1209600-1728000 | `JOB_SEARCH_PERIOD_SECONDS = 1728000` |
| Monthly runs | 30 days | 2592000 | `JOB_SEARCH_PERIOD_SECONDS = 2592000` |

**Conversion formula:**
```
Seconds = Days × 86400
```

**Examples:**
```python
# 5 days
JOB_SEARCH_PERIOD_SECONDS = 5 * 86400  # = 432000

# 2 weeks
JOB_SEARCH_PERIOD_SECONDS = 14 * 86400  # = 1209600
```

#### Step 4: Test the Changes

```bash
# Set discovery mode in config.py
# BOT_MODE = "discovery"

# Run the bot
python main.py
```

**Check the logs for:**
- ✅ `"Using JOB_SEARCH_PERIOD_SECONDS: ..."` (if using new parameter)
- ⚠️ `"Using deprecated DEFAULT_JOB_POSTED_FILTER_SECONDS"` (if using old parameter)
- ❌ No errors about missing parameters

#### Step 5: Verify Results

- Check that jobs are being discovered
- Verify the time range of discovered jobs matches your configuration
- Review logs for any errors or unexpected behavior

#### Step 6: Database - No Action Required

✅ Your existing database (`jobs.db`) is fully compatible. The `run_history` table is preserved for monitoring and statistics purposes.

### For New Users

Simply add the following to your `config.py`:

```python
# Job search period in seconds (20 days by default)
JOB_SEARCH_PERIOD_SECONDS = 1728000
```

## Rollback Instructions

If you encounter issues and need to rollback:

### Option 1: Restore from Backup

```bash
# Restore config
cp config.py.backup config.py

# Restore database
cp jobs.db.backup jobs.db
```

### Option 2: Use Backward Compatibility

Simply comment out the new parameter and the old logic will continue to work:

```python
# JOB_SEARCH_PERIOD_SECONDS = 1728000  # Commented out

# The bot will automatically fall back to DEFAULT_JOB_POSTED_FILTER_SECONDS
```

## Expected Warnings

### Using Deprecated Parameter

If you haven't added `JOB_SEARCH_PERIOD_SECONDS`, you'll see:

```
WARNING: JOB_SEARCH_PERIOD_SECONDS not found in config.py. 
Using deprecated DEFAULT_JOB_POSTED_FILTER_SECONDS: 2592000 seconds. 
Please add 'JOB_SEARCH_PERIOD_SECONDS = 1728000' to your config.py.
```

**Action:** Add `JOB_SEARCH_PERIOD_SECONDS` to your config.py

### Very Large Period

If you set a period > 90 days, you'll see:

```
WARNING: JOB_SEARCH_PERIOD_SECONDS is set to 10000000 seconds (115 days), 
which is larger than recommended. LinkedIn typically shows job postings 
up to 30-60 days old. You may get fewer results than expected.
```

**Action:** Consider using a smaller period (e.g., 20-30 days)

### Very Small Period

If you set a period < 1 day, you'll see:

```
WARNING: JOB_SEARCH_PERIOD_SECONDS is set to 3600 seconds (1.0 hours), 
which is very short. You may get very few or no results. 
Recommended minimum: 86400 seconds (1 day).
```

**Action:** Consider using at least 1 day (86400 seconds)

## Troubleshooting

### Issue: Bot not finding any jobs

**Possible causes:**
1. Period is too small
2. Period is too large (> 90 days)
3. Other search filters are too restrictive

**Solutions:**
- Try the default period: `JOB_SEARCH_PERIOD_SECONDS = 1728000` (20 days)
- Check your `KEYWORDS`, `GEO_ID`, and other search parameters
- Review logs for warnings about the period

### Issue: Seeing deprecation warning

**Cause:** You haven't added `JOB_SEARCH_PERIOD_SECONDS` to your config

**Solution:** Add the parameter as described in Step 2

### Issue: TypeError or ValueError

**Possible causes:**
1. `JOB_SEARCH_PERIOD_SECONDS` is not an integer (e.g., string or float)
2. `JOB_SEARCH_PERIOD_SECONDS` is zero or negative

**Solution:**
```python
# Correct - integer value
JOB_SEARCH_PERIOD_SECONDS = 1728000

# Incorrect - string
# JOB_SEARCH_PERIOD_SECONDS = "1728000"

# Incorrect - float
# JOB_SEARCH_PERIOD_SECONDS = 1728000.0

# Incorrect - zero or negative
# JOB_SEARCH_PERIOD_SECONDS = 0
```

## Benefits of the New Approach

1. **Predictability:** Same behavior every run
2. **Simplicity:** One clear parameter to configure
3. **Testability:** Easier to test with fixed values
4. **Flexibility:** Users control the period explicitly
5. **Transparency:** No hidden calculations based on timestamps

## FAQ

### Q: What happens to my run history in the database?

**A:** Nothing! The `run_history` table is preserved for monitoring and statistics. It's no longer used for calculating the search period, but it's still useful for tracking when the bot runs.

### Q: Do I need to change my existing database?

**A:** No, the database schema and data remain unchanged.

### Q: Can I still use `DEFAULT_JOB_POSTED_FILTER_SECONDS`?

**A:** Yes, it will work with a deprecation warning. However, we recommend migrating to `JOB_SEARCH_PERIOD_SECONDS` for clarity.

### Q: What if I run the bot irregularly (sometimes daily, sometimes weekly)?

**A:** Choose a period that covers your longest gap between runs, plus a buffer. For example, if you run weekly (7 days), use 10 days (864000 seconds).

### Q: How do I know if I chose the right period?

**A:** Check the logs and database after a run. If you're getting too few jobs, increase the period. If you're getting too many old/irrelevant jobs, decrease it.

### Q: Will this affect my application success rate?

**A:** No, this only affects which jobs are discovered. The rest of the process (enrichment, filtering, application) remains unchanged.

## Support

If you encounter any issues during migration:

1. Check the logs for specific error messages
2. Review this guide's Troubleshooting section
3. Verify your config.py syntax
4. Open an issue on the project repository with:
   - Error messages from logs
   - Your configuration (remove sensitive data)
   - Steps you've already tried

## Summary

✅ **Simple migration:** Add one new parameter to config.py  
✅ **Backward compatible:** Old config continues to work  
✅ **No database changes:** Existing data is fully compatible  
✅ **Improved clarity:** Fixed period is easier to understand  
✅ **Better control:** You decide the search period explicitly

Happy job hunting! 🚀

