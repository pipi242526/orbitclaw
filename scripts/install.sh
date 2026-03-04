#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.lunaeclaw.docker.env"
API_KEY_VAR="LUNAECLAW_API_KEY"

log() {
  printf '[install] %s\n' "$*"
}

die() {
  printf '[install][error] %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || die "缺少命令: ${cmd}"
}

read_env_default() {
  local key="$1"
  local fallback="$2"
  if [[ -f "$ENV_FILE" ]]; then
    local line
    line="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)"
    if [[ -n "$line" ]]; then
      printf '%s\n' "${line#*=}"
      return
    fi
  fi
  printf '%s\n' "$fallback"
}

prompt_with_default() {
  local label="$1"
  local default="$2"
  local value
  read -r -p "${label} [${default}]: " value
  if [[ -z "$value" ]]; then
    printf '%s\n' "$default"
    return
  fi
  printf '%s\n' "$value"
}

prompt_optional() {
  local label="$1"
  local default="${2:-}"
  local value
  if [[ -n "$default" ]]; then
    read -r -p "${label} [${default}] (回车跳过): " value
    if [[ -z "$value" ]]; then
      printf '%s\n' "$default"
      return
    fi
    printf '%s\n' "$value"
    return
  fi
  read -r -p "${label} (回车跳过): " value
  printf '%s\n' "$value"
}

prompt_secret_optional() {
  local label="$1"
  local value
  read -r -s -p "${label} (回车跳过，输入不回显): " value
  printf '\n'
  printf '%s\n' "$value"
}

prompt_yes_no() {
  local label="$1"
  local default="$2"
  local hint="Y/n"
  local value
  if [[ "$default" == "0" ]]; then
    hint="y/N"
  fi
  read -r -p "${label} (${hint}): " value
  if [[ -z "$value" ]]; then
    printf '%s\n' "$default"
    return
  fi
  case "$value" in
    y|Y|yes|YES) printf '1\n' ;;
    n|N|no|NO) printf '0\n' ;;
    *) printf '%s\n' "$default" ;;
  esac
}

validate_port() {
  local name="$1"
  local value="$2"
  if ! [[ "$value" =~ ^[0-9]+$ ]]; then
    die "${name} 端口必须是数字: ${value}"
  fi
  if (( value < 1 || value > 65535 )); then
    die "${name} 端口必须在 1-65535: ${value}"
  fi
}

upsert_env_kv() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp="${file}.tmp.$$"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  awk -v key="$key" -v value="$value" '
    BEGIN { done = 0 }
    $0 ~ ("^" key "=") {
      print key "=" value
      done = 1
      next
    }
    { print }
    END {
      if (!done) {
        print key "=" value
      }
    }
  ' "$file" >"$tmp"
  mv "$tmp" "$file"
}

normalize_path() {
  local raw="$1"
  if [[ "$raw" == "~"* ]]; then
    raw="${HOME}${raw#\~}"
  fi
  if [[ "$raw" != /* ]]; then
    raw="${ROOT_DIR}/${raw}"
  fi
  printf '%s\n' "$raw"
}

write_compose_env() {
  local compose_project_name="$1"
  local data_dir="$2"
  local gateway_port="$3"
  local webui_port="$4"
  local webui_token="$5"
  local enable_webui="$6"
  local endpoint_name="$7"

  cat >"$ENV_FILE" <<EOF
COMPOSE_PROJECT_NAME=${compose_project_name}
LUNAECLAW_DATA_DIR=${data_dir}
GATEWAY_PORT=${gateway_port}
WEBUI_PORT=${webui_port}
LUNAECLAW_WEBUI_PATH_TOKEN=${webui_token}
ENABLE_WEBUI=${enable_webui}
LUNAECLAW_ENDPOINT_NAME=${endpoint_name}
EOF
}

require_cmd docker
require_cmd python3

if ! docker compose version >/dev/null 2>&1; then
  die "检测不到 docker compose，请先安装 Docker Compose v2"
fi

log "开始配置。以下项都可回车跳过（保留默认值）。"

default_project_name="$(read_env_default COMPOSE_PROJECT_NAME lunaeclaw)"
default_data_dir="$(read_env_default LUNAECLAW_DATA_DIR "${HOME}/.lunaeclaw")"
default_gateway_port="$(read_env_default GATEWAY_PORT 18790)"
default_webui_port="$(read_env_default WEBUI_PORT 18791)"
default_webui_token="$(read_env_default LUNAECLAW_WEBUI_PATH_TOKEN "")"
default_enable_webui="$(read_env_default ENABLE_WEBUI 1)"
default_endpoint_name="$(read_env_default LUNAECLAW_ENDPOINT_NAME custom)"

compose_project_name="$(prompt_with_default "Compose 项目名" "$default_project_name")"
data_dir="$(prompt_with_default "宿主机数据目录" "$default_data_dir")"
data_dir="$(normalize_path "$data_dir")"
gateway_port="$(prompt_with_default "Gateway 端口" "$default_gateway_port")"
validate_port "Gateway" "$gateway_port"
enable_webui="$(prompt_yes_no "是否启用 WebUI 服务" "$default_enable_webui")"

webui_port="$default_webui_port"
if [[ "$enable_webui" == "1" ]]; then
  webui_port="$(prompt_with_default "WebUI 端口" "$default_webui_port")"
  validate_port "WebUI" "$webui_port"
fi

webui_token="$(prompt_optional "WebUI Path Token" "$default_webui_token")"
model_input="$(prompt_optional "机器人模型（例: openai/gpt-4o-mini 或 gpt-4o-mini）" "")"
api_base_input="$(prompt_optional "API Base URL（例: https://api.openai.com/v1）" "")"
api_key_input="$(prompt_secret_optional "API Key")"

endpoint_name="$default_endpoint_name"
if [[ -n "$api_base_input" ]]; then
  endpoint_name="$(prompt_with_default "自定义 endpoint 名称" "$default_endpoint_name")"
fi

mkdir -p "$data_dir"
touch "$data_dir/.env"
write_compose_env \
  "$compose_project_name" \
  "$data_dir" \
  "$gateway_port" \
  "$webui_port" \
  "$webui_token" \
  "$enable_webui" \
  "$endpoint_name"
log "已写入 ${ENV_FILE}"

if [[ -n "$api_key_input" ]]; then
  upsert_env_kv "$data_dir/.env" "$API_KEY_VAR" "$api_key_input"
  log "已写入 ${data_dir}/.env (${API_KEY_VAR})"
fi

if [[ -f "${data_dir}/config.json" ]]; then
  config_backup="${data_dir}/config.json.bak.$(date +%Y%m%d%H%M%S)"
  cp "${data_dir}/config.json" "$config_backup"
  log "已备份旧配置: ${config_backup}"
fi

CONFIG_PATH="${data_dir}/config.json" \
GATEWAY_PORT="$gateway_port" \
MODEL_INPUT="$model_input" \
API_BASE_INPUT="$api_base_input" \
API_KEY_INPUT="$api_key_input" \
API_KEY_VAR="$API_KEY_VAR" \
ENDPOINT_NAME="$endpoint_name" \
python3 - <<'PY'
import json
import os
from pathlib import Path

config_path = Path(os.environ["CONFIG_PATH"]).expanduser()
config_path.parent.mkdir(parents=True, exist_ok=True)

if config_path.exists():
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
else:
    data = {}

if not isinstance(data, dict):
    data = {}

providers = data.setdefault("providers", {})
if not isinstance(providers, dict):
    providers = {}
    data["providers"] = providers

agents = data.setdefault("agents", {})
if not isinstance(agents, dict):
    agents = {}
    data["agents"] = agents

defaults = agents.setdefault("defaults", {})
if not isinstance(defaults, dict):
    defaults = {}
    agents["defaults"] = defaults

gateway = data.setdefault("gateway", {})
if not isinstance(gateway, dict):
    gateway = {}
    data["gateway"] = gateway

gateway["port"] = int(os.environ["GATEWAY_PORT"])

model_input = (os.environ.get("MODEL_INPUT") or "").strip()
api_base_input = (os.environ.get("API_BASE_INPUT") or "").strip()
api_key_input = (os.environ.get("API_KEY_INPUT") or "").strip()
api_key_var = (os.environ.get("API_KEY_VAR") or "LUNAECLAW_API_KEY").strip()
endpoint_name = (os.environ.get("ENDPOINT_NAME") or "custom").strip() or "custom"
has_api_key = bool(api_key_input)

final_model = ""
if api_base_input:
    endpoints = providers.setdefault("endpoints", {})
    if not isinstance(endpoints, dict):
        endpoints = {}
        providers["endpoints"] = endpoints
    endpoint_cfg = endpoints.get(endpoint_name)
    if not isinstance(endpoint_cfg, dict):
        endpoint_cfg = {}
    endpoint_cfg["type"] = endpoint_cfg.get("type") or "openai_compatible"
    endpoint_cfg["apiBase"] = api_base_input
    endpoint_cfg["apiKey"] = f"${{{api_key_var}}}"
    if model_input:
        if "/" in model_input:
            final_model = model_input
            if final_model.startswith(endpoint_name + "/"):
                endpoint_cfg["models"] = [final_model.split("/", 1)[1]]
        else:
            final_model = f"{endpoint_name}/{model_input}"
            endpoint_cfg["models"] = [model_input]
    endpoints[endpoint_name] = endpoint_cfg
elif has_api_key:
    openai_cfg = providers.get("openai")
    if not isinstance(openai_cfg, dict):
        openai_cfg = {}
    openai_cfg["apiKey"] = f"${{{api_key_var}}}"
    providers["openai"] = openai_cfg
    if model_input:
        if "/" in model_input:
            final_model = model_input
        else:
            final_model = f"openai/{model_input}"
else:
    if model_input:
        final_model = model_input

if final_model:
    defaults["model"] = final_model

config_path.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

log "已写入 ${data_dir}/config.json"

start_now="$(prompt_yes_no "是否立即构建并启动容器" "1")"
if [[ "$start_now" == "1" ]]; then
  cd "$ROOT_DIR"
  if [[ "$enable_webui" == "1" ]]; then
    docker compose --env-file "$ENV_FILE" up -d --build lunaeclaw-gateway lunaeclaw-webui
    log "启动完成：Gateway=http://127.0.0.1:${gateway_port}  WebUI=http://127.0.0.1:${webui_port}"
  else
    docker compose --env-file "$ENV_FILE" up -d --build lunaeclaw-gateway
    log "启动完成：Gateway=http://127.0.0.1:${gateway_port}"
  fi
  log "查看日志: docker compose --env-file ${ENV_FILE} logs -f"
else
  log "稍后启动命令："
  if [[ "$enable_webui" == "1" ]]; then
    printf 'docker compose --env-file %q up -d --build lunaeclaw-gateway lunaeclaw-webui\n' "$ENV_FILE"
  else
    printf 'docker compose --env-file %q up -d --build lunaeclaw-gateway\n' "$ENV_FILE"
  fi
fi
