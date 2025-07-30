def calcul_recommande(previsions, stock_actuel, capacite_max, delai):
    stock_actuel = stock_actuel or 0
    capacite_max = capacite_max or 0
    delai = delai or 0
    demande_prevue = sum(previsions)
    commande_brute = max(0, demande_prevue - stock_actuel)
    commande_optimale = min(commande_brute, capacite_max - stock_actuel)
    return max(0, int(commande_optimale))
