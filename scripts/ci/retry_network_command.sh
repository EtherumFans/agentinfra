#!/usr/bin/env bash
set -uo pipefail

# Run network-dependent package-manager commands with bounded retries.
# A final failure always preserves the command's original exit status, so
# dependency conflicts and vulnerability findings remain blocking.
max_attempts="${CI_NETWORK_RETRY_ATTEMPTS:-3}"
initial_delay="${CI_NETWORK_RETRY_INITIAL_DELAY_SECONDS:-10}"
timeout_seconds="${CI_NETWORK_COMMAND_TIMEOUT_SECONDS:-600}"

if (( $# == 0 )); then
  echo "usage: retry_network_command.sh COMMAND [ARG ...]" >&2
  exit 64
fi

log_file="$(mktemp)"
trap 'rm -f "$log_file"' EXIT
network_error_pattern='(EAI_AGAIN|ECONNRESET|ECONNREFUSED|ENETUNREACH|ENOTFOUND|ETIMEDOUT|HTTP[^[:digit:]]*5[0-9]{2}|5[0-9]{2} (Bad Gateway|Gateway Timeout|Service Unavailable)|Temporary failure|Connection (reset|timed out)|ReadTimeout|RemoteDisconnected|audit endpoint returned an error|No matching distribution found)'

for ((attempt = 1; attempt <= max_attempts; attempt++)); do
  echo "::group::Network command attempt ${attempt}/${max_attempts}: $1"
  : > "$log_file"
  timeout --signal=TERM "${timeout_seconds}s" "$@" 2>&1 | tee "$log_file"
  status="${PIPESTATUS[0]}"
  echo "::endgroup::"

  if (( status == 0 )); then
    exit 0
  fi
  if (( status != 124 )) && ! grep -Eiq "$network_error_pattern" "$log_file"; then
    echo "Command failed without a recognized transient network error; not retrying." >&2
    exit "${status}"
  fi
  if (( attempt == max_attempts )); then
    echo "Network command failed after ${max_attempts} attempts (exit ${status})." >&2
    exit "${status}"
  fi

  delay=$((initial_delay * (2 ** (attempt - 1))))
  echo "::warning::Network command exited ${status}; retrying in ${delay}s."
  sleep "${delay}"
done
