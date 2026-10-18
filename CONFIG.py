mining_target = 5
# mining target = 5 dauert ca. 5 sekunden
#mining target = 6 dauert ca. 1 minute

import math

def abbruch_rueckstand(q, schwelle=0.001):
    """Ab welchem Rückstand liegt die Aufhol-Wahrscheinlichkeit (q/p)^n unter der Schwelle?"""
    p = 1 - q
    if q >= p:
        return 10**9          # Angreifer holt mit Sicherheit auf: praktisch nie abbrechen
    return math.ceil(math.log(schwelle) / math.log(q / p))