# Pre-Upgrade Backup Methodology

**Created:** 2026-05-13
**Purpose:** Systematic approach to backing up user data before upgrading Hermes Agent or other system components.

## When to Use
- Before any Hermes Agent upgrade (`hermes update`, git pull, etc.)
- Before any system maintenance that could wipe `/opt/hermes` or `/opt/data`
- Before any operation where files outside the three safe dirs may be deleted

## The Three Safe Directories

All user data lives under `/opt/data/`. The upgrade only touches `/opt/hermes` (application code).

| Path | Contains | Symlink? |
|------|----------|----------|
| `/opt/data/.hermes/` | Config, secrets, memory, cron jobs, content, logs | `~/.hermes → /opt/data/.hermes` |
| `/opt/data/config/` | GitHub keys, PAT, OAuth tokens, X/Twitter accounts, xurl config | `~/.config → /opt/data/config` |
| `/opt/data/home/` | Installed binaries (xurl, yt-dlp), npm packages, backlog, publications | `.git-credentials`, `.gitconfig`, `.npmrc` |

## Step 1: Inventory Everything

```bash
# See all files outside git-tracked code
cd /opt/data && find . -type f -not -path './.git/*' -not -path './__pycache__/*' -not -path './node_modules/*' | sort

# Check symlinks in home
ls -la ~ | grep -E '^l'

# Check what's under each safe directory
find /opt/data/.hermes -type f | sort
find /opt/data/config -type f | sort
find /opt/data/home -type f -not -path '*/site-packages/*' -not -path '*/.local/share/uv/*' | sort
```

## Step 2: Identify Custom vs Upstream

**Custom files (must backup):**
- `.hermes/` — entire directory
- `config/` — entire directory
- `repos/` — git repos with local state
- `scripts/` — custom script repo
- `home/.local/bin/*` — installed binaries
- `home/.npm-global/` — npm packages
- `signal-cli*` — Signal CLI
- Root-level files: `state.db`, `kanban.db`, `SOUL.md`, `.env`, `models_dev_cache.json`

**Upstream (replaced during upgrade, no backup needed):**
- `/opt/hermes/` — source code, venv, node_modules
- `/opt/data/hermes-agent/venv` — rebuilt during upgrade

## Step 3: Create Backup Tarballs

### Main archive (critical files)
```bash
cd /opt/data
tar czf backup-2026-05-13/hermes-critical-backup.tar.gz \
  --owner=0 --group=0 \
  .hermes/config.yaml .hermes/.env .hermes/auth.json .hermes/auth.lock \
  .hermes/channel_directory.json .hermes/discord_threads.json .hermes/gateway_state.json \
  .hermes/processes.json .hermes/state.db .hermes/work-queue.md \
  .hermes/YOUTUBE_TRANSCRIPT_SETUP_SUMMARY.txt .hermes/youtube-raw-transcript-setup.md \
  .hermes/yt-digest.txt \
  .hermes/memories/ .hermes/cron/jobs.json .hermes/cron/last-nightly-sync.txt \
  .hermes/cron/.tick.lock .hermes/audio_cache/ .hermes/image_cache/ \
  .hermes/content/ .hermes/logs/ \
  .env config/ \
  home/.xurl home/.git-credentials home/.gitconfig home/.npmrc \
  repos/ scripts/ \
  signal-cli signal-cli-0.14.2-Linux-native.tar.gz \
  home/publications/ home/backlog/ \
  kanban.db SOUL.md state.db models_dev_cache.json
```

### Secondary archive (large pieces that can't append to gzip)
```bash
# Cron output and installed binaries
tar czf backup-2026-05-13/hermes-missing-pieces.tar.gz \
  --owner=0 --group=0 \
  .hermes/cron/output/ \
  home/.local/bin/xurl \
  home/.npm-global/
```

## Step 4: Write Restore Instructions

Create a `README-restore.txt` in the backup directory with:
1. What's in the backup
2. Restore commands
3. Verification steps (check symlinks, permissions, critical files)
4. Post-restore checklist

## Pitfalls & Tips

### Symlinks are transparent
`~/.hermes`, `~/.config`, `~/backlog`, `~/publications` are all symlinks to `/opt/data/`. Backup using the `/opt/data/` path. After extract, symlinks should still work.

### Tar cannot update compressed archives
If you forget something, you CANNOT append to a `.tar.gz`. Create a separate archive instead.

### Cron output is often missed
`.hermes/cron/output/` contains months of cron job results. It's small (~1-2MB) but easy to forget.

### Installed binaries need separate handling
xurl (13MB), yt-dlp venv, etc. live in `home/.local/` and won't be in any git repo.

### Permissions after extract
After `tar xzf`, files extracted as root may have wrong ownership. Run:
```bash
chown -R hermes:hermes /opt/data/.hermes /opt/data/config /opt/data/repos /opt/data/scripts /opt/data/state.db* /opt/data/kanban.db /opt/data/.env
```

### Two tarballs is fine
If one archive gets huge (e.g., 400+ YouTube transcript files), splitting into "critical" + "large-optional" is a valid strategy.

## Post-Restore Checklist
1. Verify symlinks: `ls -la ~ | grep -E '^l'`
2. Check auth: `ls -la /opt/data/.hermes/auth.json`
3. Check cron: `ls -la /opt/data/.hermes/cron/jobs.json`
4. Check memory: `ls -la /opt/data/.hermes/memories/MEMORY.md`
5. Check GitHub keys: `ls -la /opt/data/config/github/hermes-agent`
6. Check xurl: `ls -la /opt/data/home/.local/bin/xurl`
7. Start gateway and verify platforms respond
8. Check cron jobs are scheduled
