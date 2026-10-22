"""### CAMBIO AQUÍ ### Corre todas las pruebas automáticas y dice cuáles fallaron.

En tu compu (con un Postgres local de prueba, NUNCA el de Render/Neon):
    set PRUEBAS_OK=1
    set PRUEBAS_DATABASE_URL=postgresql://postgres@localhost:5432/postgres
    python tests/correr.py
En GitHub corre solo en cada push (ver .github/workflows/pruebas.yml).
"""
import os, re, subprocess, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

def main():
    suites = sorted(f for f in os.listdir(AQUI) if f.startswith("test_") and f.endswith(".py"))
    if len(sys.argv) > 1:
        suites = [s for s in suites if any(x in s for x in sys.argv[1:])]
    total_ok, malas = 0, []
    for s in suites:
        t0 = time.time()
        r = subprocess.run([sys.executable, os.path.join(AQUI, s), RAIZ], capture_output=True, text=True, timeout=600)
        salida = r.stdout + r.stderr
        ok = len(re.findall(r"^OK ", salida, re.M))
        xx = re.findall(r"^XX .*", salida, re.M)
        total_ok += ok
        estado = "bien" if ok and not xx else "FALLÓ"
        print(f"{estado:6} {s:24} {ok:3} chequeos  {time.time() - t0:5.1f} s")
        if xx or not ok:
            malas.append(s)
            for linea in (xx or salida.strip().splitlines()[-8:])[:8]:
                print("        " + linea)
    print(f"\n{total_ok} chequeos bien, {len(malas)} prueba(s) con problemas" + (f": {', '.join(malas)}" if malas else ""))
    sys.exit(1 if malas else 0)

if __name__ == "__main__":
    main()
