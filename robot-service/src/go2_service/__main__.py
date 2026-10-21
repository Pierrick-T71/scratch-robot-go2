"""Point d'entrée du service.

Lancement :
    python -m go2_service

Ce point d'entrée est le SEUL à configurer la journalisation : il coupe le
flot du SDK Unitree avant de créer l'application (voir
`main._couper_le_flot_du_sdk`). Un lancement direct par uvicorn ne bénéficierait
pas de ce réglage.

Le choix du port et de l'interface vient de `shared/safety-limits.json`.
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
        level=logging.WARNING,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
    )

    # Le SDK Unitree journalise CHAQUE message sur le logger racine, au niveau
    # INFO. Mesuré : 474 Mo de journal en 2 h, et une latence de 4,1 s sur
    # l'état du robot. On coupe ce flot AVANT de créer l'application ; notre
    # propre logger reste à INFO (voir `main._couper_le_flot_du_sdk`).
    from .main import _couper_le_flot_du_sdk

    _couper_le_flot_du_sdk()

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