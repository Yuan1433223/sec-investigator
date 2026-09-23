from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    env: str = "dev"
    debug: bool = False
    log_level: str = "INFO"


class ModelSettings(BaseSettings):
    # Provider switch: "openai" (default) or "anthropic"
    llm_provider: str = "openai"

    # OpenAI-compatible (Dashscope / vLLM / Ollama etc.)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    plus_model_name: str = "gpt-4o"
    flash_model_name: str = "gpt-4o-mini"

    # Anthropic (direct or relay endpoint)
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    claude_model_name: str = "claude-sonnet-4-6"
    claude_flash_model_name: str = "claude-sonnet-4-6"

    # Local / OpenAI-compatible endpoint (vLLM, Ollama, LM Studio, etc.)
    local_model_base: str = "http://localhost:11434/v1"
    local_model_name: str = "llama3"
    local_model_api_key: str = "local"

    # LangSmith tracing (optional)
    langsmith_tracing: str = "false"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_api_key: str = ""
    langsmith_project: str = "kks-next"

    # Backwards-compat: old field name openai_api_base also accepted via alias
    @property
    def openai_api_base(self) -> str:
        return self.openai_base_url


class StorageSettings(BaseSettings):
    postgres_dsn: str = "postgresql://localhost/kks"
    sqlite_path: str = "./kks_dev.db"
    redis_url: str = "redis://localhost:6379/0"


class ESSettings(BaseSettings):
    # Elasticsearch — base URL + credentials
    # The full URLs from old system encode creds inline; we separate them here.
    es_url: str = "http://localhost:9200"
    es_username: str = ""
    es_password: str = ""
    # Index patterns
    es_waf_index: str = "waf_full_log*"
    es_gf_index: str = "gamedun-full-logs*"
    es_alarm_index: str = "security_analysis_alarm*"
    es_request_timeout: int = 30


class PrometheusSettings(BaseSettings):
    # Old system used PROMETHEUS_API_KEY for the URL (misleading name kept via alias)
    prometheus_url: str = "http://localhost:9090"
    prometheus_request_timeout: int = 30
    prometheus_node_port: int = 64998


class SecurityAPISettings(BaseSettings):
    # CC protection API
    cc_api_url: str = ""
    cc_api_key: str = ""
    cc_request_timeout: int = 30

    # DDoS protection API
    ddos_api_url: str = ""
    ddos_api_key: str = ""
    ddos_token: str = ""
    ddos_request_timeout: int = 30

    # Evidence thresholds (code-level policy)
    cc_attack_pps_threshold: int = 2000
    cc_attack_delta_threshold: int = 1000
    ddos_attack_kbps_threshold: int = 1_000_000


class GFSettings(BaseSettings):
    gf_yxd_api_url: str = ""
    gf_yxd_api_xtoken: str = ""
    gf_cdn_api_url: str = ""
    gf_cdn_api_xtoken: str = ""
    gf_ddos_api_url: str = ""
    gf_ddos_api_xtoken: str = ""
    gf_request_timeout: int = 10


class WAFSettings(BaseSettings):
    waf_api_url: str = ""
    waf_api_token: str = ""
    waf_request_timeout: int = 10


class FeishuSettings(BaseSettings):
    feishu_alert_webhook_url: str = ""


class RAGSettings(BaseSettings):
    milvus_host: str = "localhost"
    milvus_port: int = 19531
    milvus_user: str = "root"
    milvus_password: str = ""
    mongodb_host: str = "localhost"
    mongodb_port: int = 27017
    mongodb_user: str = ""
    mongodb_password: str = ""
    rag_embedding_model: str = "text-embedding-v4"
    rag_embedding_dimensions: int = 1536
    rag_score_threshold: float = 0.6
    rag_top_k: int = 5
    rag_default_team_id: str = ""
    rag_default_dataset_id: str = ""


class Settings(
    AppSettings, ModelSettings, StorageSettings,
    ESSettings, PrometheusSettings, SecurityAPISettings,
    GFSettings, WAFSettings, FeishuSettings, RAGSettings,
):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def get_settings() -> Settings:
    return Settings()
