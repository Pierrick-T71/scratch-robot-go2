"""Service robot GO2 Scratch.

Ce paquet est le service intermédiaire entre l'éditeur Blockly (frontend
Svelte, sur PC Windows) et le robot Unitree Go2 (via `unitree_sdk2py`, sur
machine Linux).

Règles structurantes :
  - le mode initial est TOUJOURS la simulation ;
  - aucune commande basse niveau (moteurs, CRC32, `rt/lowcmd`) ;
  - le service reste responsable de l'arrêt, jamais l'interface ;
  - une commande non supportée est refusée, jamais improvisée.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]