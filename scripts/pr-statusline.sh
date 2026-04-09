#!/bin/bash
#
# Claude Code PR Status Line
#
# Displays: 🤖 Model (Context: 🟢 X% | MCP: N/M | $X.XX) | 📂 Directory | 🌿 Branch [commits] | PR#N [status]
#
# COMMIT STATUS (vs remote tracking branch):
#   ↑N      = N commits ahead (unpushed)
#   ↓N      = N commits behind (need to pull)
#   ↑N↓M    = Diverged (N ahead, M behind)
#   (none)  = In sync with remote
#
# PR CI CHECKS:
#   ⏳      = No checks started yet
#   🔄(N)   = N checks running/pending
#   ✅      = All checks passed
#   ❌(N)   = N checks failed
#
# PR REVIEW STATUS:
#   ✅      = Approved
#   🔴      = Changes requested
#   👀      = Review required
#   ⚪      = No reviews yet
#
# PR COMMENTS:
#   💬N     = N comments on PR
#   (none)  = No comments
#
# MODEL INFO (in parentheses after model name):
#   Context: 🟢 Z% (Xk/Yk)  = Usage <= 40% (safe)
#   Context: 🟡 Z% (Xk/Yk)  = Usage 41-59% (moderate)
#   Context: 🟠 Z% (Xk/Yk)  = Usage 60-79% (warning)
#   Context: 🔴 Z% (Xk/Yk)  = Usage >= 80% (critical)
#   MCP: N/M          = N enabled / M total MCP servers
#   $X.XX             = Total session cost in USD
#   Separator: | (vertical bar between sections)
#
# Cache: PR/GitHub data cached for 10 seconds (session data always fresh)
#

# Read Claude session data
input=$(cat)

# Extract basic info
model=$(echo "$input" | jq -r '.model.display_name // .model.displayName // "unknown"')
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // "unknown"')
dir=$(basename "$cwd")
session_cost=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')

# Extract context window data from official API fields
context_size=$(echo "$input" | jq -r '.context_window.context_window_size // 0')
current_usage=$(echo "$input" | jq -r '.context_window.current_usage // empty')

# Calculate context usage: outputs "current_tokens context_size percentage"
calculate_context_usage() {
    # If context_size is invalid, return empty (unknown)
    if [ -z "$context_size" ] || [ "$context_size" = "null" ] || \
       ! [[ "$context_size" =~ ^[0-9]+$ ]] || [ "$context_size" -eq 0 ]; then
        echo ""
        return
    fi

    # If no usage data yet, return 0 (session just started)
    if [ -z "$current_usage" ] || [ "$current_usage" = "null" ]; then
        echo "0 $context_size 0"
        return
    fi

    local input_tokens=$(echo "$current_usage" | jq -r '.input_tokens // 0')
    local cache_creation=$(echo "$current_usage" | jq -r '.cache_creation_input_tokens // 0')
    local cache_read=$(echo "$current_usage" | jq -r '.cache_read_input_tokens // 0')
    local current_tokens=$((${input_tokens:-0} + ${cache_creation:-0} + ${cache_read:-0}))

    if [ "$current_tokens" -eq 0 ]; then
        echo "0 $context_size 0"
        return
    fi

    local context_pct=$((current_tokens * 100 / context_size))

    # Cap at 100%
    if [ "$context_pct" -gt 100 ]; then
        context_pct=100
    fi

    echo "$current_tokens $context_size $context_pct"
}

# Format token count as raw integer for <1000, otherwise Xk or X.Yk notation
format_tokens_k() {
    local tokens=$1
    echo "$tokens" | awk '{
        if ($1 < 1000) {
            printf "%d", $1
        } else {
            v = $1 / 1000
            if (v == int(v)) printf "%dk", v
            else printf "%.1fk", v
        }
    }'
}

# Count MCP servers and return enabled/total format
count_mcp_servers_enabled_total() {
    local total=0
    local disabled=0

    # User-level MCP servers from ~/.claude.json
    if [ -f "$HOME/.claude.json" ]; then
        local user_count=$(jq '.mcpServers | length // 0' "$HOME/.claude.json" 2>/dev/null)
        if [ -n "$user_count" ] && [ "$user_count" != "null" ]; then
            total=$((total + user_count))
        fi

        # Project-specific servers from projects[cwd].mcpServers
        local project_servers=$(jq --arg cwd "$cwd" '.projects[$cwd].mcpServers | length // 0' "$HOME/.claude.json" 2>/dev/null)
        if [ -n "$project_servers" ] && [ "$project_servers" != "null" ]; then
            total=$((total + project_servers))
        fi

        # Disabled servers for this project
        local disabled_count=$(jq --arg cwd "$cwd" '.projects[$cwd].disabledMcpServers | length // 0' "$HOME/.claude.json" 2>/dev/null)
        if [ -n "$disabled_count" ] && [ "$disabled_count" != "null" ]; then
            disabled=$disabled_count
        fi
    fi

    # Project-level MCP servers from .mcp.json (separate file)
    if [ -f "$cwd/.mcp.json" ]; then
        local mcp_json_count=$(jq '.mcpServers | length // 0' "$cwd/.mcp.json" 2>/dev/null)
        if [ -n "$mcp_json_count" ] && [ "$mcp_json_count" != "null" ]; then
            total=$((total + mcp_json_count))
        fi

        # Count disabled servers in .mcp.json (servers with disabled: true)
        local mcp_json_disabled=$(jq '[.mcpServers | to_entries[] | select(.value.disabled == true)] | length // 0' "$cwd/.mcp.json" 2>/dev/null)
        if [ -n "$mcp_json_disabled" ] && [ "$mcp_json_disabled" != "null" ]; then
            disabled=$((disabled + mcp_json_disabled))
        fi
    fi

    local enabled=$((total - disabled))
    [ $enabled -lt 0 ] && enabled=0

    echo "$enabled/$total"
}

# Get git branch
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "🤖 $model | 📂 $dir | ⚠️  Not a git repo"
    exit 0
fi

branch=$(git branch --show-current 2>/dev/null || echo "detached")

# Check commits ahead/behind remote
commit_status=""
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null)
if [ -n "$upstream" ]; then
    ahead=$(git rev-list --count @{u}..HEAD 2>/dev/null || echo "0")
    behind=$(git rev-list --count HEAD..@{u} 2>/dev/null || echo "0")

    if [ "$ahead" -gt 0 ] && [ "$behind" -gt 0 ]; then
        commit_status=" ↑${ahead}↓${behind}"
    elif [ "$ahead" -gt 0 ]; then
        commit_status=" ↑${ahead}"
    elif [ "$behind" -gt 0 ]; then
        commit_status=" ↓${behind}"
    fi
fi

# Calculate context percentage and apply color coding
context_display=""
context_data=$(calculate_context_usage)

if [ -n "$context_data" ]; then
    read -r ctx_current ctx_max context_pct <<< "$context_data"
    current_k=$(format_tokens_k "$ctx_current")
    max_k=$(format_tokens_k "$ctx_max")

    # Colored emoji by severity: <=40% green, <60% yellow, <80% orange, >=80% red
    if [ "$context_pct" -le 40 ]; then
        status_icon="🟢"
    elif [ "$context_pct" -lt 60 ]; then
        status_icon="🟡"
    elif [ "$context_pct" -lt 80 ]; then
        status_icon="🟠"
    else
        status_icon="🔴"
    fi
    context_display="Context: ${status_icon} ${context_pct}% (${current_k}/${max_k})"
fi

# Get MCP server counts (enabled/total)
mcp_counts=$(count_mcp_servers_enabled_total)
mcp_display=""
if [ "$mcp_counts" != "0/0" ]; then
    mcp_display="MCP: $mcp_counts"
fi

# Format cost display
cost_display=""
if [ "$session_cost" != "0" ] && [ -n "$session_cost" ]; then
    cost_display=$(printf "\$%.2f" "$session_cost")
fi

# Build model info with context, MCP, and cost in parentheses
model_info="🤖 $model"
info_parts=""
[ -n "$context_display" ] && info_parts="$context_display"
[ -n "$mcp_display" ] && info_parts="${info_parts:+$info_parts | }$mcp_display"
[ -n "$cost_display" ] && info_parts="${info_parts:+$info_parts | }$cost_display"

if [ -n "$info_parts" ]; then
    model_info="$model_info ($info_parts)"
fi

# Cache only PR/GitHub API data to avoid rate limits (10 second TTL)
# Session-specific data (model, context, cost, MCP) is always computed fresh above
safe_branch=$(echo "$branch" | sed 's/\//_/g')
pr_cache_file="/tmp/claude-pr-data-$safe_branch"
cache_age=10
pr_section=""

# Check if cached PR data is still fresh
use_cache=false
if [ -f "$pr_cache_file" ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
        cache_time=$(stat -f %m "$pr_cache_file" 2>/dev/null)
    else
        cache_time=$(stat -c %Y "$pr_cache_file" 2>/dev/null)
    fi

    # Guard against empty/non-integer cache_time (stat failure, race condition)
    if [ -n "$cache_time" ] && [[ "$cache_time" =~ ^[0-9]+$ ]]; then
        current_time=$(date +%s)
        age=$((current_time - cache_time))
    else
        age=$cache_age  # Force refresh if cache_time is invalid
    fi

    if [ $age -lt $cache_age ]; then
        pr_section=$(cat "$pr_cache_file")
        use_cache=true
    fi
fi

if [ "$use_cache" = false ]; then
    # Check if there's a PR for this branch
    pr_data=$(gh pr view "$branch" --json number,state,statusCheckRollup,reviewDecision,comments 2>/dev/null)

    if [ $? -ne 0 ] || [ -z "$pr_data" ]; then
        # No PR found
        pr_section="📝 No PR"
    else
        # Parse PR data
        pr_number=$(echo "$pr_data" | jq -r '.number')

        # Check CI status (handle both CheckRun and StatusContext types)
        all_checks=$(echo "$pr_data" | jq -r '.statusCheckRollup | length')
        failed_checks=$(echo "$pr_data" | jq -r '[.statusCheckRollup[] | select(.conclusion == "FAILURE" or .state == "FAILURE")] | length')
        pending_checks=$(echo "$pr_data" | jq -r '[.statusCheckRollup[] | select(.conclusion == "PENDING" or .status == "IN_PROGRESS" or .status == "QUEUED" or .state == "PENDING" or (.status == "COMPLETED" and .conclusion == null))] | length')

        # Determine CI emoji
        if [ "$all_checks" -eq 0 ]; then
            ci_status="⏳"  # No checks yet
        elif [ "$failed_checks" -gt 0 ]; then
            ci_status="❌($failed_checks)"  # Failed checks
        elif [ "$pending_checks" -gt 0 ]; then
            ci_status="🔄($pending_checks)"  # Pending checks
        else
            ci_status="✅"  # All passed
        fi

        # Check review status
        review_decision=$(echo "$pr_data" | jq -r '.reviewDecision // "NONE"')
        case "$review_decision" in
            "APPROVED")
                review_status="✅"
                ;;
            "CHANGES_REQUESTED")
                review_status="🔴"
                ;;
            "REVIEW_REQUIRED")
                review_status="👀"
                ;;
            *)
                review_status="⚪"
                ;;
        esac

        # Count comments
        comment_count=$(echo "$pr_data" | jq -r '.comments | length')
        if [ "$comment_count" -gt 0 ]; then
            comment_status="💬$comment_count"
        else
            comment_status=""
        fi

        pr_section="PR#$pr_number $ci_status $review_status $comment_status"
    fi

    # Cache only the PR section
    printf '%s' "$pr_section" > "$pr_cache_file"
fi

# Build output: fresh session data + cached PR data
output="$model_info | 📂 $dir | 🌿 $branch$commit_status | $pr_section"

printf '%s\n' "$output"
