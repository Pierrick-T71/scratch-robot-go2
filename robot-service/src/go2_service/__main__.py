"""Point d'entrée du service.

Lancement en développement :
    uvicorn go2_service.main:app --host 127.0.0.1 --port 8765

Le choix du port et de l'interface vient de `shared/safety-limits.json`.
Voir `python -m go2_service` pour un lancement avec ces valeurs par défaut.
"""

from __future__ import annotations

import argparse
import logging

from .config import load_limits


def main() -> None:
    """Lance le service avec les valeurs de `shared/safety-limits.json`.

    Par défaut l'écoute se fait sur la boucle locale uniquement. Exposer le
    service sur le réseau est une décision délibérée qui suppose de lire
    d'abord `docs/SAFETY.md` (section « Exposition réseau »).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    )

    limits = load_limits()

    parser = argparse.ArgumentParser(description="Service robot GO2 Scratch")
    parser.add_argument(
        "--host",
        default=limits.service.host,
        help="Interface d'écoute (par défaut : boucle locale).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=limits.service.port,
        help="Port d'écoute.",
    )
    args = parser.parse_args()

    if args.host not in ("127.0.0.1", "::1", "localhost"):
        logging.getLogger(__name__).warning(
            "Écoute sur %s : le service est exposé hors de cette machine. "
            "Vérifiez docs/SAFETY.md avant de continuer.",
            args.host,
        )

    import uvicorn

    from .main import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()