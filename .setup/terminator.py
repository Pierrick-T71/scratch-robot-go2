"""Genere le theme « Terminator » (arrangement synthetise, original).

Aucune bande originale n'est utilisee : chaque note est fabriquee ici.
Le motif emblematique du film de Brad Fiedel (1984) est une pulsation de
basse en 5/4 — La, La, La, La, Sol — soulignee de frappes metalliques,
sur laquelle descend une ligne de synthetiseur.

Le haut-parleur du Go2 est petit : la basse est ecrite avec beaucoup
d'harmoniques pour rester audible, et la melodie est placee haut.
"""

from __future__ import annotations

import sys
import wave

import numpy as np

SR = 48_000
BPM = 100.0
TEMPS = 60.0 / BPM
MESURE = 5 * TEMPS
NB_MESURES = 12
DUREE = NB_MESURES * MESURE + 2.5

# Frequences utiles (gamme de La mineur).
A1, A2, G2 = 55.0, 110.0, 98.0
A3, B3, C4, D4, E4, F4, G4, A4 = 220.0, 246.94, 261.63, 293.66, 329.63, 349.23, 392.0, 440.0

rng = np.random.default_rng(1984)


def _enveloppe(n: int, attaque: float, chute: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1.0, t / attaque) * np.exp(-t / chute)


def note_basse(frequence: float, duree: float = 0.5) -> np.ndarray:
    """Pulsation grave, riche en harmoniques, attaque franche."""
    n = int(duree * SR)
    t = np.arange(n) / SR
    phase = 2 * np.pi * frequence * t
    onde = np.zeros(n)
    for rang in range(1, 9):
        onde += np.sin(rang * phase) / rang**1.1
    onde += 0.45 * np.sin(phase * 0.5)  # sous-octave, discret
    return onde * _enveloppe(n, 0.004, 0.11) * 0.5


def frappe_metallique(duree: float = 0.55) -> np.ndarray:
    """Coup industriel : partiels inharmoniques + souffle."""
    n = int(duree * SR)
    t = np.arange(n) / SR
    onde = np.zeros(n)
    for frequence, amplitude in ((1180, 0.5), (1870, 0.35), (2630, 0.25), (3910, 0.12)):
        onde += amplitude * np.sin(2 * np.pi * frequence * t + rng.uniform(0, 6.28))
    onde = 0.55 * onde + 0.45 * rng.normal(0, 1, n)
    return onde * np.exp(-t / 0.09) * 0.3


def battement(duree: float = 0.3) -> np.ndarray:
    """Battement de coeur : sinus grave qui descend."""
    n = int(duree * SR)
    t = np.arange(n) / SR
    frequence = 38 + 25 * np.exp(-t / 0.05)
    phase = 2 * np.pi * np.cumsum(frequence) / SR
    return np.sin(phase) * np.exp(-t / 0.07) * 0.85


def note_melodie(frequence: float, duree: float) -> np.ndarray:
    """Nappe de synthetiseur, legerement desaccordee et vibrante."""
    n = int(duree * SR)
    t = np.arange(n) / SR
    vibrato = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * t)
    phase = 2 * np.pi * np.cumsum(frequence * vibrato) / SR
    onde = np.zeros(n)
    for rang in (1, 3, 5, 7):
        onde += np.sin(rang * phase) / rang
    desaccord = 2 * np.pi * np.cumsum(frequence * 1.004 * vibrato) / SR
    onde += 0.5 * np.sin(desaccord)
    entree = np.minimum(1.0, t / 0.09)
    sortie = np.minimum(1.0, (duree - t) / 0.35)
    return onde * entree * sortie * 0.2


def poser(piste: np.ndarray, signal: np.ndarray, debut_s: float) -> None:
    debut = int(debut_s * SR)
    fin = min(len(piste), debut + len(signal))
    if fin > debut:
        piste[debut:fin] += signal[: fin - debut]


def construire() -> np.ndarray:
    piste = np.zeros(int(DUREE * SR))

    for mesure in range(NB_MESURES):
        debut = mesure * MESURE

        # Battement de coeur : present de l'introduction au premier theme.
        if mesure < 4:
            poser(piste, battement(), debut + 0.02)
            poser(piste, battement(), debut + 0.26)

        # Ostinato : 4 fois La, puis Sol. Il porte tout le morceau.
        if mesure >= 2:
            for temps in range(5):
                frequence = A2 if temps < 4 else G2
                poser(piste, note_basse(frequence), debut + temps * TEMPS)

        # Frappe metallique sur le premier temps, a partir de la mesure 3.
        if mesure >= 2:
            poser(piste, frappe_metallique(), debut)

        # Petit tic mecanique sur les temps suivants.
        if mesure >= 2:
            for temps in range(1, 5):
                n = int(0.03 * SR)
                tic = rng.normal(0, 1, n) * np.exp(-np.arange(n) / (0.006 * SR))
                poser(piste, tic * 0.06, debut + temps * TEMPS)

    # Ligne descendante, une note par mesure, de la mesure 5 a la 12.
    descente = [A4, G4, F4, E4, D4, C4, B3, A3]
    for indice, frequence in enumerate(descente):
        poser(piste, note_melodie(frequence, MESURE * 1.05), (4 + indice) * MESURE)

    # Final : accord grave tenu et derniere frappe.
    poser(piste, note_basse(A1, 2.4), NB_MESURES * MESURE)
    poser(piste, frappe_metallique(0.9), NB_MESURES * MESURE)
    poser(piste, note_melodie(A4, 2.2), NB_MESURES * MESURE)

    # Petit espace : quelques copies retardees et attenuees.
    for retard_ms, gain in ((95, 0.28), (170, 0.18), (260, 0.11)):
        retard = int(retard_ms / 1000 * SR)
        piste[retard:] += gain * piste[:-retard].copy()

    piste /= max(1e-9, np.max(np.abs(piste)))
    return np.tanh(piste * 1.1) * 0.89


def ecrire(chemin: str) -> None:
    signal = construire()
    stereo = np.stack([signal, signal], axis=1)
    donnees = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(chemin, "wb") as fichier:
        fichier.setnchannels(2)
        fichier.setsampwidth(2)
        fichier.setframerate(SR)
        fichier.writeframes(donnees.tobytes())


if __name__ == "__main__":
    destination = sys.argv[1] if len(sys.argv) > 1 else "terminator.wav"
    ecrire(destination)
    print(f"{destination} ecrit : {DUREE:.1f} s, {SR} Hz, stereo")
