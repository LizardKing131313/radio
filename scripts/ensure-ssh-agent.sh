#!/usr/bin/env bash
set -euo pipefail

key_path="${RADIO_SSH_KEY:-$HOME/.ssh/id_ed25519}"
env_path="${RADIO_SSH_AGENT_ENV:-$HOME/.ssh/radio-agent.env}"

mkdir -p "$(dirname "$env_path")"

if [[ -f "$env_path" ]]; then
  # Reuse the agent started by an earlier Ansible command when it is alive.
  # shellcheck disable=SC1090
  if ! source <(grep -E '^export SSH_(AUTH_SOCK|AGENT_PID)=' "$env_path"); then
    unset SSH_AUTH_SOCK SSH_AGENT_PID
    rm -f "$env_path"
  fi
fi

if ! ssh-add -l >/dev/null 2>&1; then
  eval "$(ssh-agent -s)" >/dev/null
  {
    printf 'export SSH_AUTH_SOCK=%q\n' "$SSH_AUTH_SOCK"
    printf 'export SSH_AGENT_PID=%q\n' "$SSH_AGENT_PID"
  } >"$env_path"
  chmod 600 "$env_path"
  ssh-add "$key_path" >&2
fi

printf 'export SSH_AUTH_SOCK=%q; export SSH_AGENT_PID=%q\n' "$SSH_AUTH_SOCK" "$SSH_AGENT_PID"
