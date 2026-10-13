# Source this in WSL before running uv in this repo:
#   source scripts/wsl-env.sh
# Keeps the virtualenv and caches on the Linux filesystem (fast imports) while the
# repo itself stays on the Windows drive.
export PATH="$HOME/.local/bin:$PATH"
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/surf-clipper"
export UV_LINK_MODE=copy
# IPv6 is unreachable from this WSL network; make Node (npm) prefer IPv4.
export NODE_OPTIONS="--dns-result-order=ipv4first"
export NVM_DIR="$HOME/.nvm"
# shellcheck disable=SC1091
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
