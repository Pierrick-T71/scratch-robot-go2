import logging.config
import uvicorn

cfg = uvicorn.config.LOGGING_CONFIG
print("cles uvicorn :", sorted(cfg.keys()))
print("root dans la config uvicorn :", "root" in cfg)
print("disable_existing_loggers :", cfg.get("disable_existing_loggers"))
print("loggers uvicorn :", sorted(cfg.get("loggers", {}).keys()))
