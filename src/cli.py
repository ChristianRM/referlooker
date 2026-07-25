import os
import json
import csv
import time

# Códigos de color ANSI para mejorar la estética en la terminal
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"

def clear_screen():
    """Limpia la consola dependiendo del sistema operativo."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header(title):
    """Imprime un encabezado estilizado en la consola."""
    width = 70
    print("\n" + "=" * width)
    print(f"{BOLD}{CYAN}{title.center(width)}{RESET}")
    print("=" * width)

def load_candidates(json_path="output/candidatos.json"):
    """Carga los candidatos desde candidatos.json y los agrupa por vacante."""
    if not os.path.exists(json_path):
        return {}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"{RED}[Error] No se pudo leer {json_path}: {e}{RESET}")
        return {}

    candidatos_deseables = data.get("candidatos_deseables", [])
    candidatos_no_deseables = data.get("candidatos_no_deseables", [])

    # Agrupar por vacante
    vacancies = {}
    
    def add_to_group(cand_list, group_name):
        for cand in cand_list:
            vac_name = cand.get("vacante", "Sin Vacante Asignada")
            if vac_name not in vacancies:
                vacancies[vac_name] = {"deseables": [], "no_deseables": []}
            # Asegurar tipo de score
            try:
                cand["score"] = int(cand.get("score", 0))
            except Exception:
                cand["score"] = 0
            vacancies[vac_name][group_name].append(cand)

    add_to_group(candidatos_deseables, "deseables")
    add_to_group(candidatos_no_deseables, "no_deseables")

    return vacancies

def print_candidates_table(candidates):
    """Dibuja una tabla ASCII con los candidatos y retorna la lista mapeada por índice."""
    if not candidates:
        print(f"{YELLOW}No se encontraron candidatos para mostrar con los filtros aplicados.{RESET}")
        return []

    # Encabezado de la tabla
    col_idx = " # "
    col_name = "Nombre"
    col_score = "Score"
    col_otw = "OpenToWork"
    col_loc = "Ubicación"

    print(f"+-----+---------------------------+-------+------------+---------------------------------+")
    print(f"|{BOLD}{WHITE}{col_idx:^3}{RESET}|{BOLD}{WHITE}{col_name:^27}{RESET}|{BOLD}{WHITE}{col_score:^7}{RESET}|{BOLD}{WHITE}{col_otw:^12}{RESET}|{BOLD}{WHITE}{col_loc:^33}{RESET}|")
    print(f"+-----+---------------------------+-------+------------+---------------------------------+")

    mapped = []
    for i, c in enumerate(candidates, 1):
        mapped.append(c)
        name = c.get("nombre", "Desconocido")[:25]
        score = c.get("score", 0)
        open_to_work = "Sí" if c.get("open_to_work") else "No"
        location = c.get("location", "No especificada")[:31]

        # Formato de colores según score y disponibilidad
        score_color = GREEN if score >= 85 else (YELLOW if score >= 60 else RED)
        otw_color = GREEN if c.get("open_to_work") else RESET
        
        # Formatear celdas con ancho fijo
        name_str = f"{name:<25}"
        score_str = f"{score:>4}%"
        otw_str = f"{open_to_work:^10}"
        loc_str = f"{location:<31}"

        print(f"| {i:^3} | {name_str} | {score_color}{score_str}{RESET} | {otw_color}{otw_str}{RESET} | {loc_str} |")

    print(f"+-----+---------------------------+-------+------------+---------------------------------+")
    return mapped

def view_candidate_detail(candidate):
    """Muestra la información detallada de un candidato seleccionado."""
    clear_screen()
    print_header(f"Ficha Detallada: {candidate.get('nombre')}")
    
    score = candidate.get("score", 0)
    score_color = GREEN if score >= 85 else (YELLOW if score >= 60 else RED)
    open_to_work = f"{GREEN}Sí (Búsqueda Activa){RESET}" if candidate.get("open_to_work") else "No / No detectado"

    print(f"{BOLD}Vacante Asociada:{RESET} {candidate.get('vacante')}")
    print(f"{BOLD}URL LinkedIn:{RESET}     {candidate.get('linkedin_url')}")
    print(f"{BOLD}Ubicación:{RESET}        {candidate.get('location')}")
    print(f"{BOLD}Puntuación Match:{RESET} {score_color}{score}%{RESET}")
    print(f"{BOLD}Open to Work:{RESET}     {open_to_work}")
    print(f"{BOLD}Titular:{RESET}          {candidate.get('titular')}")
    print(f"{BOLD}Fecha Registro:{RESET}   {candidate.get('timestamp', 'N/A')}")
    print("-" * 70)
    
    print(f"{BOLD}{CYAN}[Resumen de Evaluación Ollama]{RESET}")
    print(candidate.get("resumen_evaluacion", "Sin resumen de evaluación disponible."))
    print("-" * 70)

    # Mostrar secciones colapsables o simplificadas
    print(f"{BOLD}{CYAN}[Acerca de / Extracto]{RESET}")
    acerca = candidate.get("acerca_de", "").strip()
    print(acerca if acerca else "Sección vacía o no disponible.")
    print("-" * 70)

    print(f"{BOLD}{CYAN}[Experiencia Profesional (Resumen)]{RESET}")
    exp = candidate.get("experiencia", "").strip()
    if exp:
        # Mostrar las primeras 15 líneas para no inundar la consola
        lines = exp.split('\n')
        if len(lines) > 15:
            print('\n'.join(lines[:15]))
            print(f"{YELLOW}... [Perfil contiene {len(lines)} líneas de experiencia. Ver perfil de LinkedIn completo para más detalles] ...{RESET}")
        else:
            print(exp)
    else:
        print("Sección vacía o no disponible.")
    print("-" * 70)

    print(f"{BOLD}{CYAN}[Habilidades]{RESET}")
    habs = candidate.get("habilidades", "").strip()
    if habs:
        # Formatear habilidades si vienen muy largas
        lines = habs.split('\n')
        skills = [l.strip() for l in lines if l.strip() and not l.strip().startswith("Skills") and not l.strip().startswith("All") and not l.strip().startswith("Tools") and not l.strip().startswith("Industry")]
        if skills:
            print(", ".join(skills[:30]))
            if len(skills) > 30:
                print(f"{YELLOW}... y {len(skills) - 30} habilidades más.{RESET}")
        else:
            print(habs[:300])
    else:
        print("Sección vacía o no disponible.")
    
    print("=" * 70)
    input(f"\nPresiona {BOLD}[Enter]{RESET} para regresar a la lista de candidatos...")

def export_vacancy_to_csv(vac_name, candidates):
    """Exporta los candidatos filtrados de una vacante a un archivo CSV."""
    # Sanitizar el nombre del archivo
    safe_name = "".join(c for c in vac_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
    safe_name = safe_name.replace(" ", "_")
    filename = f"output/{safe_name}_export.csv"

    fieldnames = ["Nombre", "Score", "Open to Work", "LinkedIn URL", "Ubicación", "Titular", "Resumen Evaluación"]
    
    try:
        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for c in candidates:
                writer.writerow({
                    "Nombre": c.get("nombre", ""),
                    "Score": f"{c.get('score', 0)}%",
                    "Open to Work": "Sí" if c.get("open_to_work") else "No",
                    "LinkedIn URL": c.get("linkedin_url", ""),
                    "Ubicación": c.get("location", ""),
                    "Titular": c.get("titular", ""),
                    "Resumen Evaluación": c.get("resumen_evaluacion", "")
                })
        print(f"\n{GREEN}[Éxito] Reporte exportado a: {os.path.abspath(filename)}{RESET}")
        input(f"Presiona {BOLD}[Enter]{RESET} para continuar...")
    except Exception as e:
        print(f"\n{RED}[Error] No se pudo exportar a CSV: {e}{RESET}")
        input(f"Presiona {BOLD}[Enter]{RESET} para continuar...")

def filter_candidates_menu(all_candidates):
    """Menú secundario para aplicar filtros sobre una lista de candidatos."""
    filtered = all_candidates.copy()
    
    while True:
        clear_screen()
        print_header(f"Filtro de Candidatos (Resultados Actuales: {len(filtered)})")
        
        print("1. Filtrar por Score Mínimo")
        print("2. Filtrar por estado 'Open to Work'")
        print("3. Filtrar por Ubicación / País (Búsqueda por texto)")
        print("4. Buscar palabra clave en Perfil (Nombre, Titular, Habilidades)")
        print("5. Restablecer todos los filtros")
        print("6. Ver candidatos resultantes")
        print("q. Salir al menú de vacante")
        
        opc = input(f"\nSeleccione una opción: ").strip()
        
        if opc == "1":
            try:
                min_score = int(input("Ingrese el score mínimo (0-100): ").strip())
                filtered = [c for c in filtered if c.get("score", 0) >= min_score]
            except ValueError:
                print(f"{RED}Valor inválido.{RESET}")
                input("Presione Enter...")
        elif opc == "2":
            otw_input = input("¿Mostrar sólo candidatos Open to Work? (S/N): ").strip().lower()
            if otw_input in ("s", "si", "y", "yes"):
                filtered = [c for c in filtered if c.get("open_to_work")]
            elif otw_input in ("n", "no"):
                filtered = [c for c in filtered if not c.get("open_to_work")]
        elif opc == "3":
            loc_query = input("Ingrese país, estado o palabra clave de ubicación: ").strip().lower()
            if loc_query:
                filtered = [c for c in filtered if loc_query in c.get("location", "").lower()]
        elif opc == "4":
            keyword = input("Ingrese término de búsqueda: ").strip().lower()
            if keyword:
                filtered = [c for c in filtered if (
                    keyword in c.get("nombre", "").lower() or
                    keyword in c.get("titular", "").lower() or
                    keyword in c.get("habilidades", "").lower() or
                    keyword in c.get("experiencia", "").lower() or
                    keyword in c.get("acerca_de", "").lower()
                )]
        elif opc == "5":
            filtered = all_candidates.copy()
            print(f"{GREEN}Filtros restablecidos.{RESET}")
            input("Presione Enter...")
        elif opc == "6":
            # Mostrar la tabla resultante directamente desde el filtro
            clear_screen()
            print_header(f"Candidatos Filtrados ({len(filtered)})")
            mapped = print_candidates_table(filtered)
            if mapped:
                idx = input(f"\nIngrese el número de candidato para ver detalle o {BOLD}[Enter]{RESET} para regresar: ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(mapped):
                    view_candidate_detail(mapped[int(idx) - 1])
            else:
                input("\nPresione Enter para regresar...")
        elif opc.lower() == "q":
            break
            
    return filtered

def manage_vacancy_candidates(vac_name, data):
    """Menú para administrar/visualizar los candidatos de una vacante específica."""
    deseables = data.get("deseables", [])
    no_deseables = data.get("no_deseables", [])
    all_cands = deseables + no_deseables
    
    # Ordenar por score descendente por defecto
    all_cands.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    current_list = all_cands.copy()

    while True:
        clear_screen()
        print_header(f"Vacante: {vac_name}")
        print(f"Resumen de candidatos:")
        print(f"- Deseables (Score >= 85): {GREEN}{len(deseables)}{RESET}")
        print(f"- No Deseables (Score < 85): {RED}{len(no_deseables)}{RESET}")
        print(f"- Visualizando actualmente: {BOLD}{len(current_list)}{RESET} candidatos\n")

        print("1. Ver Todos los candidatos")
        print("2. Ver sólo candidatos Deseables")
        print("3. Ver sólo candidatos No Deseables")
        print("4. Aplicar Filtros Avanzados y Búsqueda")
        print("5. Exportar esta lista a CSV")
        print("q. Regresar al menú anterior")
        
        opc = input(f"\nSeleccione una opción: ").strip()

        if opc == "1":
            current_list = all_cands.copy()
            clear_screen()
            print_header(f"Todos los Candidatos ({len(current_list)})")
            mapped = print_candidates_table(current_list)
            if mapped:
                idx = input(f"\nIngrese el número de candidato para ver detalle o {BOLD}[Enter]{RESET} para regresar: ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(mapped):
                    view_candidate_detail(mapped[int(idx) - 1])
        elif opc == "2":
            current_list = deseables.copy()
            clear_screen()
            print_header(f"Candidatos Deseables ({len(current_list)})")
            mapped = print_candidates_table(current_list)
            if mapped:
                idx = input(f"\nIngrese el número de candidato para ver detalle o {BOLD}[Enter]{RESET} para regresar: ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(mapped):
                    view_candidate_detail(mapped[int(idx) - 1])
        elif opc == "3":
            current_list = no_deseables.copy()
            clear_screen()
            print_header(f"Candidatos No Deseables ({len(current_list)})")
            mapped = print_candidates_table(current_list)
            if mapped:
                idx = input(f"\nIngrese el número de candidato para ver detalle o {BOLD}[Enter]{RESET} para regresar: ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(mapped):
                    view_candidate_detail(mapped[int(idx) - 1])
        elif opc == "4":
            current_list = filter_candidates_menu(all_cands)
        elif opc == "5":
            export_vacancy_to_csv(vac_name, current_list)
        elif opc.lower() == "q":
            break

def run_cli():
    """Inicia el bucle principal del CLI de candidatos."""
    while True:
        clear_screen()
        print_header("ReferLooker - Navegador y Filtro de Candidatos")
        
        vacancies = load_candidates()
        
        if not vacancies:
            print(f"\n{YELLOW}No se encontraron registros de candidatos en 'output/candidatos.json'.{RESET}")
            print("Asegúrate de procesar vacantes primero para poblar la base de datos.")
            input(f"\nPresiona {BOLD}[Enter]{RESET} para regresar...")
            break

        print("Selecciona una vacante para explorar sus candidatos:\n")
        
        mapped_vacs = []
        for i, (vac_name, data) in enumerate(vacancies.items(), 1):
            mapped_vacs.append((vac_name, data))
            num_des = len(data["deseables"])
            num_ndes = len(data["no_deseables"])
            print(f"{BOLD}{i:>2}.{RESET} {vac_name:<60} [{GREEN}{num_des} Deseables{RESET} | {RED}{num_ndes} No Deseables{RESET}]")

        print(f"\n{BOLD} q.{RESET} Volver al menú principal")

        selection = input(f"\nSelecciona una opción: ").strip()

        if selection.lower() == 'q':
            break

        if selection.isdigit():
            idx = int(selection)
            if 1 <= idx <= len(mapped_vacs):
                vac_name, data = mapped_vacs[idx - 1]
                manage_vacancy_candidates(vac_name, data)
            else:
                print(f"{RED}Opción inválida. Reintente.{RESET}")
                time.sleep(1)
        else:
            print(f"{RED}Opción inválida. Reintente.{RESET}")
            time.sleep(1)

if __name__ == "__main__":
    import time
    # Si se ejecuta directamente, iniciar CLI
    run_cli()
