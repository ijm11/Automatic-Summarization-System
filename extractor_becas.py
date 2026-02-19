import fitz  # PyMuPDF
import json
import csv
import re
from pathlib import Path

class SistemaExtraccionBecas:
    def __init__(self, carpeta_entrada):
        self.ruta_data = Path(carpeta_entrada)
        self.datos_extraidos = []

    def clean_text(self, text):
        """Limpia el texto de espacios extra y saltos de línea innecesarios."""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text).strip()

    def extract_academic_year(self, text, filename):
        """Extrae el curso académico."""
        # Buscar en el título o primeras líneas
        match = re.search(r"CURSO ACADÉMICO (20\d{2}-20\d{2})", text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # Fallback al nombre del archivo
        match = re.search(r"20\d{2}-20\d{2}", filename)
        if match:
            return match.group(0)
        
        match = re.search(r"20\d{2}-\d{2}", filename)
        if match:
            parts = match.group(0).split('-')
            return f"20{parts[0][2:]}-20{parts[1]}"
            
        return "Desconocido"

    def extract_programs(self, text):
        """Extrae las enseñanzas comprendidas (Artículo 3)."""
        programs = []
        # Patrón para capturar el contenido del Artículo 3 hasta el Capítulo II
        pattern = r"Artículo 3\. Enseñanzas comprendidas\.(.*?)CAPÍTULO II"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        
        if match:
            content = match.group(1)
            # Limpiar patrones de pie de página/cabecera que puedan haberse colado
            content = re.sub(r"CSV :.*", "", content)
            content = re.sub(r"FIRMANTE.*", "", content)
            content = re.sub(r"DIRECCIÓN DE VALIDACIÓN.*", "", content)
            
            # Buscar líneas que parecen elementos de lista
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                # Filtrar líneas cortas o basura
                if len(line) > 10 and not line.isdigit() and "Página" not in line: 
                    programs.append(line)
        
        # Unir y limpiar
        full_text = " ".join(programs)
        full_text = self.clean_text(full_text)
        return full_text if full_text else "No detectado"

    def extract_amounts(self, text):
        """Extrae las cuantías de las becas (Artículo 11 aprox)."""
        amounts = {}
        
        # Cuantía fija ligada a la renta
        renta_match = re.search(r"Cuantía fija ligada a la renta.*?:?\s*([\d\.,]+)\s*euros", text, re.IGNORECASE)
        amounts["cuantia_renta_fija"] = renta_match.group(1) if renta_match else "No detectado"
        
        # Cuantía fija ligada a la residencia
        residencia_match = re.search(r"Cuantía fija ligada a la residencia.*?:?\s*([\d\.,]+)\s*euros", text, re.IGNORECASE)
        amounts["cuantia_residencia"] = residencia_match.group(1) if residencia_match else "No detectado"
        
        # Beca básica
        basica_match = re.search(r"Beca básica.*?:?\s*([\d\.,]+)\s*euros", text, re.IGNORECASE)
        amounts["beca_basica"] = basica_match.group(1) if basica_match else "No detectado"
        
        # Cuantía variable mínima
        variable_match = re.search(r"cuantía variable.*?importe mínimo.*?([\d\.,]+)\s*euros", text, re.IGNORECASE)
        if not variable_match:
             variable_match = re.search(r"cuantía variable.*?mínimo será de\s*([\d\.,]+)\s*euros", text, re.IGNORECASE)

        amounts["cuantia_variable_minima"] = variable_match.group(1) if variable_match else "60,00" # Valor común
        
        # Excelencia Range
        # Buscar "entre X y Y euros" cerca de "excelencia"
        excelencia_match = re.search(r"excelencia académica.*?:.*?entre\s*([\d\.,]+)\s*y\s*([\d\.,]+)\s*euros", text, re.IGNORECASE | re.DOTALL)
        if excelencia_match:
            amounts["excelencia_min"] = excelencia_match.group(1)
            amounts["excelencia_max"] = excelencia_match.group(2)
        else:
             # Fallback: buscar tabla de excelencia
             # 8,00 y 8,49 puntos 50 euros
             # 9,50 puntos o más 125 euros
             min_match = re.search(r"50\s*euros", text) # Muy genérico, pero bueno
             max_match = re.search(r"125\s*euros", text)
             amounts["excelencia_min"] = "50" if min_match else "No detectado"
             amounts["excelencia_max"] = "125" if max_match else "No detectado"

        return amounts

    def extract_thresholds(self, text):
        """Extrae los umbrales de renta (Artículo 19)."""
        thresholds = {}
        
        # Intentar extraer el bloque del Artículo 19
        start_pattern = r"Artículo 1?9\. Umbrales de renta.*?"
        match = re.search(start_pattern, text, re.IGNORECASE)
        
        if not match:
            return "No detectado"
            
        start_pos = match.end()
        # Buscar el fin del artículo (suele ser Artículo 20)
        end_match = re.search(r"Artículo 2?0\.", text[start_pos:])
        end_pos = start_pos + end_match.start() if end_match else min(start_pos + 5000, len(text))
        
        content = text[start_pos:end_pos]
        
        # Estrategia 1: Formato Lista
        list_found = False
        for i in range(1, 4):
            umbral_key = f"Umbral {i}"
            section_match = re.search(rf"{umbral_key}:(.*?)(?:Umbral {i+1}|Artículo 20|$)", content, re.DOTALL | re.IGNORECASE)
            if section_match:
                section_text = section_match.group(1)
                t_vals = {}
                members_matches = re.finditer(r"Familias de ([a-z]+|\d+) miembros?:?\s*([\d\.,]+)\s*euros", section_text, re.IGNORECASE)
                for m in members_matches:
                    t_vals[m.group(1)] = m.group(2)
                if t_vals:
                     thresholds[umbral_key] = t_vals
                     list_found = True

        # Estrategia 2: Formato Tabla (Single Line or Multi Line)
        if not list_found:
            table_data = []
            lines = content.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # Caso A: Todo en una línea: 1 8.843 13.898 14.818
                table_match = re.match(r"^(\d+)\s+([\d\.]+)\s+([\d\.]+)(?:\s+([\d\.]+))?", line)
                if table_match and int(table_match.group(1)) < 20: # Filtro de seguridad
                     table_data.append({
                        "miembros": table_match.group(1),
                        "umbral_1": table_match.group(2),
                        "umbral_2": table_match.group(3),
                        "umbral_3": table_match.group(4) if table_match.group(4) else "N/A"
                    })
                     i += 1
                     continue

                # Caso B: Dividido en líneas (PyMuPDF row-wise split)
                # 1
                # 8.843
                # 13.898
                # ...
                if re.match(r"^\d+$", line) and int(line) < 20:
                    members = line
                    # Buscar siguientes 2 o 3 líneas con formato de monto
                    vals = []
                    lookahead = 1
                    while looks_like_amount(lines, i + lookahead):
                         vals.append(lines[i + lookahead].strip())
                         lookahead += 1
                         if len(vals) >= 3: break
                    
                    if len(vals) >= 2: # Al menos 2 umbrales
                        table_data.append({
                            "miembros": members,
                            "umbral_1": vals[0],
                            "umbral_2": vals[1],
                            "umbral_3": vals[2] if len(vals) > 2 else "N/A"
                        })
                        i += lookahead
                        continue
                
                i += 1

            if table_data:
                thresholds["tabla"] = table_data

        return thresholds

    def extract_patrimonio_thresholds(self, text):
        """Extracts asset/patrimonio thresholds (Article 20)."""
        result = {}

        match = re.search(r"Artículo 20\..*?Umbrales indicativos de patrimonio familiar\.(.*?)Artículo 21\.", text, re.DOTALL | re.IGNORECASE)
        if not match:
            match = re.search(r"umbrales indicativos de patrimonio familiar\.(.*?)(?:Artículo 21|CAPÍTULO)", text, re.DOTALL | re.IGNORECASE)

        if match:
            content = self.clean_text(match.group(1))

            # Urban property limit
            urban = re.search(r"fincas urbanas.*?superar.*?([\d\.,]+)\s*euros", content, re.IGNORECASE)
            if urban:
                result["fincas_urbanas_limite"] = urban.group(1)

            # Rural constructions limit
            rural_const = re.search(r"construcciones situadas en fincas rústicas.*?superar.*?([\d\.,]+)\s*euros", content, re.IGNORECASE)
            if rural_const:
                result["construcciones_rusticas_limite"] = rural_const.group(1)

            # Rural land limit per member
            rural_land = re.search(r"fincas rústicas excluidos.*?superar.*?([\d\.,]+)\s*euros.*?miembro", content, re.IGNORECASE)
            if rural_land:
                result["fincas_rusticas_limite_por_miembro"] = rural_land.group(1)

            # Capital/movable assets limit
            capital = re.search(r"capital mobiliario.*?superar\s*([\d\.,]+)\s*euros", content, re.IGNORECASE)
            if capital:
                result["capital_mobiliario_limite"] = capital.group(1)

        return result if result else "No detectado"

    def extract_academic_requirements(self, text):
        """Extracts academic requirements: credit minimums and pass-rate table."""
        result = {}

        # Minimum credits for full-time (Article 23)
        credits_match = re.search(r"matriculados?.*?de\s+(\d+)\s+créditos.*?tiempo\s+completo", text, re.IGNORECASE | re.DOTALL)
        if credits_match:
            result["creditos_tiempo_completo"] = int(credits_match.group(1))

        # Minimum credits for partial enrollment
        partial_match = re.search(r"(?:matrícula parcial|matricularse de un mínimo de)\s*.*?(\d+)\s+créditos", text, re.IGNORECASE | re.DOTALL)
        if partial_match:
            result["creditos_matricula_parcial"] = int(partial_match.group(1))

        # First-year university entry grade
        entry_match = re.search(r"requerirá.*?nota de\s+([\d,]+)\s+puntos.*?acceso", text, re.IGNORECASE | re.DOTALL)
        if entry_match:
            result["nota_acceso_universidad"] = entry_match.group(1)

        # Credit pass-rate table by knowledge area (Article 24)
        pass_rates = {}
        areas = [
            (r"Artes y Humanidades\s*[.\s]*\n?\s*(\d+)\s*%", "Artes y Humanidades"),
            (r"Ciencias\s*[.\s]*\n?\s*(\d+)\s*%", "Ciencias"),
            (r"Ciencias Sociales y Jurídicas\s*[.\s]*\n?\s*(\d+)\s*%", "Ciencias Sociales y Jurídicas"),
            (r"Ciencias de la Salud\s*[.\s]*\n?\s*(\d+)\s*%", "Ciencias de la Salud"),
            (r"Ingeniería o Arquitectura.*?\n?\s*(\d+)\s*%", "Ingeniería y Arquitectura"),
        ]
        for pattern, area_name in areas:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                pass_rates[area_name] = f"{m.group(1)}%"

        if pass_rates:
            result["porcentaje_creditos_por_rama"] = pass_rates

        return result if result else "No detectado"

    def extract_excellence_brackets(self, text):
        """Extracts the 4-tier excellence grade bracket table."""
        brackets = []

        # Pattern: "Entre X,XX y X,XX puntos" followed by amount
        bracket_patterns = [
            (r"(?:Entre\s+)?8,00\s+y\s+8,49\s+puntos\s*\n?\s*(\d+)\s*euros", "8.00-8.49"),
            (r"(?:Entre\s+)?8,50\s+y\s+8,99\s+puntos\s*\n?\s*(\d+)\s*euros", "8.50-8.99"),
            (r"(?:Entre\s+)?9,00\s+y\s+9,49\s+puntos\s*\n?\s*(\d+)\s*euros", "9.00-9.49"),
            (r"9,50\s+puntos\s+o\s+más\s*\n?\s*(\d+)\s*euros", "9.50+"),
        ]

        for pattern, grade_range in bracket_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                brackets.append({
                    "nota_media": grade_range,
                    "cuantia_euros": int(m.group(1))
                })

        return brackets if brackets else "No detectado"

    def extract_insular_supplements(self, text):
        """Extracts additional amounts for island/Ceuta/Melilla students (Article 12)."""
        result = {}

        match = re.search(r"Artículo 12\..*?(?:domicilio insular|Cuantías adicionales)(.*?)Artículo 13\.", text, re.DOTALL | re.IGNORECASE)
        if not match:
            return "No detectado"

        content = match.group(1)
        flags = re.IGNORECASE | re.DOTALL

        # Basic island supplement
        basic = re.search(r"dispondrán de\s*([\d\.,]+)\s*euros", content, flags)
        if basic:
            result["suplemento_insular_basico"] = basic.group(1)

        # Remote islands supplement (Lanzarote, Fuerteventura, etc.)
        remote = re.search(r"(?:adicional será de|adicional de)\s*([\d\.,]+)\s*euros.*?(?:Lanzarote|Fuerteventura)", content, flags)
        if not remote:
            remote = re.search(r"([\d\.,]+)\s*euros.*?(?:Lanzarote|Fuerteventura)", content, flags)
        if remote:
            result["suplemento_islas_remotas"] = remote.group(1)

        # Inter-island to Peninsula
        peninsula_amounts = re.findall(r"serán\s*(?:de\s*)?([\d\.,]+)\s*euros\s*y\s*([\d\.,]+)\s*euros", content, flags)
        if peninsula_amounts:
            result["suplemento_interinsular_peninsula"] = peninsula_amounts[0][0]
            result["suplemento_interinsular_peninsula_remotas"] = peninsula_amounts[0][1]

        # FP Canarias extra (only in newer years)
        fp_extra = re.search(r"incrementarán en\s*([\d\.,]+)\s*euros", content, flags)
        if fp_extra:
            result["suplemento_fp_canarias"] = fp_extra.group(1)

        return result if result else "No detectado"

    def extract_income_deductions(self, text):
        """Extracts income deductions applied to family income calculation."""
        result = {}

        # Extract the deductions section to avoid false matches elsewhere
        ded_match = re.search(r"deducciones siguientes:(.*?)(?:Artículo \d+\.|CAPÍTULO)", text, re.DOTALL | re.IGNORECASE)
        ded_text = ded_match.group(1) if ded_match else text

        # Use DOTALL for all patterns since deduction text spans multiple lines
        flags = re.IGNORECASE | re.DOTALL

        # Large family general: "525,00 euros...familias numerosas de categoría general"
        familia_gral = re.search(r"(\d[\d\.,]*)\s*euros.*?familias numerosas de categoría general", ded_text, flags)
        if familia_gral:
            result["deduccion_familia_numerosa_general"] = familia_gral.group(1)

        # Large family special: "y 800,00 euros para familias numerosas de categoría especial"
        familia_esp = re.search(r"categoría general y\s*([\d\.,]+)\s*euros", ded_text, flags)
        if not familia_esp:
            familia_esp = re.search(r"([\d\.,]+)\s*euros.*?familias numerosas de categoría especial", ded_text, flags)
        if familia_esp:
            result["deduccion_familia_numerosa_especial"] = familia_esp.group(1)

        # Disability 33%+: "c) 1.811,00 euros...discapacidad...treinta y tres"
        disc_33 = re.search(r"c\)\s*([\d\.,]+)\s*euros.*?discapacidad.*?treinta y tres", ded_text, flags)
        if disc_33:
            result["deduccion_discapacidad_33"] = disc_33.group(1)

        # Disability 65%+: "y 2.881,00 euros cuando la discapacidad...sesenta y cinco"
        disc_65 = re.search(r"treinta y tres por\s*ciento\s*y\s*([\d\.,]+)\s*euros", ded_text, flags)
        if disc_65:
            result["deduccion_discapacidad_65"] = disc_65.group(1)

        # University applicant 65%+ disability: "dicho solicitante\nserá de 4.000,00 euros"
        disc_uni = re.search(r"dicho solicitante\s*será\s*de\s*([\d\.,]+)\s*euros", ded_text, flags)
        if disc_uni:
            result["deduccion_discapacidad_65_universitario"] = disc_uni.group(1)

        # Sibling studying away: "d) 1.176,00 euros por cada hermano...resida fuera"
        hermano_fuera = re.search(r"d\)\s*([\d\.,]+)\s*euros.*?hermano.*?resida fuera", ded_text, flags)
        if hermano_fuera:
            result["deduccion_hermano_universitario_fuera"] = hermano_fuera.group(1)

        # Orphan: "e) El 20 % de la renta familiar...huérfano"
        huerfano = re.search(r"e\)\s*(?:El\s*)?(\d+)\s*(?:%|por\s*ciento)", ded_text, flags)
        if huerfano:
            result["deduccion_huerfano_porcentaje"] = f"{huerfano.group(1)}%"

        # Single-parent family: "f) 500,00 euros...monoparental"
        mono = re.search(r"f\)\s*([\d\.,]+)\s*euros.*?monoparental", ded_text, flags)
        if mono:
            result["deduccion_familia_monoparental"] = mono.group(1)

        return result if result else "No detectado"

    def extract_disability_provisions(self, text):
        """Extracts disability-related provisions (Article 13)."""
        result = {}

        match = re.search(r"Artículo 13\..*?(?:discapacidad|Becas especiales)(.*?)Artículo 14\.", text, re.DOTALL | re.IGNORECASE)
        if not match:
            return "No detectado"

        content = self.clean_text(match.group(1))

        # Reduced credit load threshold
        if re.search(r"65 por\s*ciento.*?reducir.*?carga lectiva", content, re.IGNORECASE) or \
           re.search(r"discapacidad.*?65.*?reducir", content, re.IGNORECASE):
            result["reduccion_carga_lectiva"] = "Discapacidad >= 65%"

        # 25% increment for 25-65% disability
        incr_25 = re.search(r"incremento.*?(\d+) por\s*ciento.*?discapacidad.*?25.*?65", content, re.IGNORECASE)
        if not incr_25:
            incr_25 = re.search(r"(\d+) por\s*ciento.*?discapacidad igual o superior al 25", content, re.IGNORECASE)
        if incr_25:
            result["incremento_discapacidad_25_65"] = f"{incr_25.group(1)}%"

        # 50% increase for full enrollment with disability
        incr_50 = re.search(r"incrementarán en un (\d+) por\s*ciento", content, re.IGNORECASE)
        if incr_50:
            result["incremento_matricula_completa_discapacidad"] = f"{incr_50.group(1)}%"

        return result if result else "No detectado"

    def extract_deadlines(self, text):
        """Extrae plazos de solicitud."""
        deadlines = {}
        
        # Buscar sección de plazos.
        match = re.search(r"(?:Artículo \d+\.\s*)?(?:Lugar y )?Plazo de presentación de solicitudes\.(.*?)(?:Artículo|CAPÍTULO)", text, re.DOTALL | re.IGNORECASE)
        
        content = match.group(1) if match else ""
        if not content:
             match = re.search(r"plazos? para presentar la solicitud.*?(?=\. \d)", text, re.DOTALL | re.IGNORECASE)
             if match: content = match.group(0)

        if content:
            content_clean = self.clean_text(content)
            # Buscar fechas
            dates = re.findall(r"(\d{1,2} de \w+ de \d{4})", content_clean)
            deadlines["fechas_encontradas"] = dates
            
            uni_match = re.search(r"estudiantes universitarios.*?(?:hasta el|día)\s*(\d{1,2} de \w+ de \d{4})", content_clean, re.IGNORECASE)
            if not uni_match: uni_match = re.search(r"(\d{1,2} de \w+ de \d{4}).*?estudiantes universitarios", content_clean, re.IGNORECASE)

            non_uni_match = re.search(r"estudiantes no universitarios.*?(?:hasta el|día)\s*(\d{1,2} de \w+ de \d{4})", content_clean, re.IGNORECASE)
            if not non_uni_match: non_uni_match = re.search(r"(\d{1,2} de \w+ de \d{4}).*?estudiantes no universitarios", content_clean, re.IGNORECASE)

            if uni_match: deadlines["universitarios"] = uni_match.group(1)
            if non_uni_match: deadlines["no_universitarios"] = non_uni_match.group(1)
                
            deadlines["texto_extracto"] = content_clean[:200]
        else:
            deadlines["status"] = "No detectado"
            
        return deadlines

    def ejecutar(self):
        # Verificar si la carpeta existe
        if not self.ruta_data.exists():
            print(f"Error: La carpeta '{self.ruta_data}' no existe.")
            return

        # Listar y procesar PDFs
        archivos_pdf = list(self.ruta_data.glob("*.pdf"))
        print(f"--- Iniciando procesamiento de {len(archivos_pdf)} archivos ---")

        for ruta_pdf in archivos_pdf:
            print(f"Procesando: {ruta_pdf.name}...")
            try:
                doc = fitz.open(ruta_pdf)
                texto_completo = "".join([pagina.get_text() for pagina in doc])
                
                info = {
                    "fichero": ruta_pdf.name,
                    "curso_academico": self.extract_academic_year(texto_completo, ruta_pdf.name),
                    "programas_educativos": self.extract_programs(texto_completo),
                    **self.extract_amounts(texto_completo),
                    "excelencia_tramos": self.extract_excellence_brackets(texto_completo),
                    "umbrales_renta": self.extract_thresholds(texto_completo),
                    "umbrales_patrimonio": self.extract_patrimonio_thresholds(texto_completo),
                    "requisitos_academicos": self.extract_academic_requirements(texto_completo),
                    "suplementos_insulares": self.extract_insular_supplements(texto_completo),
                    "deducciones_renta": self.extract_income_deductions(texto_completo),
                    "discapacidad": self.extract_disability_provisions(texto_completo),
                    "plazos_solicitud": self.extract_deadlines(texto_completo)
                }
                
                self.datos_extraidos.append(info)
                doc.close()
            except Exception as e:
                print(f"Error al leer {ruta_pdf.name}: {e}")

        self.guardar_resultados()

    def guardar_resultados(self):
        # Guardar en JSON
        with open("becas_estructuradas.json", "w", encoding="utf-8") as f:
            json.dump(self.datos_extraidos, f, indent=4, ensure_ascii=False)
        
        # Guardar en CSV
        if self.datos_extraidos:
            csv_data = []
            nested_fields = [
                "umbrales_renta", "umbrales_patrimonio", "requisitos_academicos",
                "excelencia_tramos", "suplementos_insulares", "deducciones_renta",
                "discapacidad", "plazos_solicitud"
            ]
            for item in self.datos_extraidos:
                row = item.copy()
                for field in nested_fields:
                    if field in row and isinstance(row[field], (dict, list)):
                        row[field] = json.dumps(row[field], ensure_ascii=False)
                if len(row.get("programas_educativos", "")) > 500:
                    row["programas_educativos"] = row["programas_educativos"][:500] + "..."
                csv_data.append(row)

            columnas = csv_data[0].keys()
            with open("becas_estructuradas.csv", "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=columnas)
                writer.writeheader()
                writer.writerows(csv_data)
        
        print("\n--- ¡Proceso finalizado! ---")
        print("Archivos generados: 'becas_estructuradas.json' y 'becas_estructuradas.csv'")

def looks_like_amount(lines, idx):
    if idx >= len(lines): return False
    # Busca 12.345 o 1.234
    return bool(re.match(r"^[\d\.]+$", lines[idx].strip()))

if __name__ == "__main__":
    sistema = SistemaExtraccionBecas(carpeta_entrada="data")
    sistema.ejecutar()
