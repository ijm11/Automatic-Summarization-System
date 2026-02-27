import fitz  # PyMuPDF library for PDF processing
import json
import csv
import re
from pathlib import Path

class SistemaExtraccionBecas:
    """
    This class handles the extraction of scholarship data from PDF files.
    It uses regular expressions (regex) to find specific sections like amounts, 
    thresholds, and requirements.
    """
    def __init__(self, carpeta_entrada):
        # We define the folder where the PDFs are located and an empty list for findings
        self.ruta_data = Path(carpeta_entrada)
        self.datos_extraidos = []

    def clean_text(self, text):
        """Cleans up the text by removing extra spaces and messy line breaks."""
        if not text:
            return ""
        return re.sub(r'\s+', ' ', text).strip()

    def extract_academic_year(self, text, filename):
        """Identifies the academic year (e.g., 2023-2024) from the text or filename."""
        # First, we look for the pattern in the document's header
        match = re.search(r"CURSO ACADÉMICO (20\d{2}-20\d{2})", text, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # If not found there, we try to guess it from the filename itself
        match = re.search(r"20\d{2}-20\d{2}", filename)
        if match:
            return match.group(0)
        
        match = re.search(r"20\d{2}-\d{2}", filename)
        if match:
            parts = match.group(0).split('-')
            return f"20{parts[0][2:]}-20{parts[1]}"
            
        return "Desconocido"

    def extract_programs(self, text):
        """Extracts the educational programs covered by the grant (Found in Article 3)."""
        programs = []
        # We look specifically between "Article 3" and the start of "Chapter II"
        pattern = r"Artículo 3\. Enseñanzas comprendidas\.(.*?)CAPÍTULO II"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        
        if match:
            content = match.group(1)
            # We remove common PDF "noise" like digital signatures or validation codes
            content = re.sub(r"CSV :.*", "", content)
            content = re.sub(r"FIRMANTE.*", "", content)
            content = re.sub(r"DIRECCIÓN DE VALIDACIÓN.*", "", content)
            
            # We split by line to find individual items in the list
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                # Skip lines that are too short or just numbers (like page numbers)
                if len(line) > 10 and not line.isdigit() and "Página" not in line: 
                    programs.append(line)
        
        # Merge everything into a clean string
        full_text = " ".join(programs)
        full_text = self.clean_text(full_text)
        return full_text if full_text else "No detectado"

    def extract_amounts(self, text):
        """Extracts the specific financial amounts for various scholarship components."""
        amounts = {}
        
        # 1. Fixed amount tied to income
        renta_match = re.search(r"Cuantía fija ligada a la renta.*?:?\s*([\d\.,]+)\s*euros", text, re.IGNORECASE)
        amounts["cuantia_renta_fija"] = renta_match.group(1) if renta_match else "No detectado"
        
        # 2. Fixed amount for residency (living away from home)
        residencia_match = re.search(r"Cuantía fija ligada a la residencia.*?:?\s*([\d\.,]+)\s*euros", text, re.IGNORECASE)
        amounts["cuantia_residencia"] = residencia_match.group(1) if residencia_match else "No detectado"
        
        # 3. Basic scholarship
        basica_match = re.search(r"Beca básica.*?:?\s*([\d\.,]+)\s*euros", text, re.IGNORECASE)
        amounts["beca_basica"] = basica_match.group(1) if basica_match else "No detectado"
        
        # 4. Variable amount (minimum)
        variable_match = re.search(r"cuantía variable.*?importe mínimo.*?([\d\.,]+)\s*euros", text, re.IGNORECASE)
        if not variable_match:
             variable_match = re.search(r"cuantía variable.*?mínimo será de\s*([\d\.,]+)\s*euros", text, re.IGNORECASE)

        amounts["cuantia_variable_minima"] = variable_match.group(1) if variable_match else "60,00" # Defaults to 60€
        
        # 5. Excellence bonuses (Academic performance)
        excelencia_match = re.search(r"excelencia académica.*?:.*?entre\s*([\d\.,]+)\s*y\s*([\d\.,]+)\s*euros", text, re.IGNORECASE | re.DOTALL)
        if excelencia_match:
            amounts["excelencia_min"] = excelencia_match.group(1)
            amounts["excelencia_max"] = excelencia_match.group(2)
        else:
             # If the range isn't explicitly stated, we search for common values like 50€ and 125€
             min_match = re.search(r"50\s*euros", text)
             max_match = re.search(r"125\s*euros", text)
             amounts["excelencia_min"] = "50" if min_match else "No detectado"
             amounts["excelencia_max"] = "125" if max_match else "No detectado"

        return amounts

    def extract_thresholds(self, text):
        """Extracts family income thresholds (how much money the family can earn)."""
        thresholds = {}
        
        # Look for Article 19 section
        start_pattern = r"Artículo 1?9\. Umbrales de renta.*?"
        match = re.search(start_pattern, text, re.IGNORECASE)
        
        if not match:
            return "No detectado"
            
        start_pos = match.end()
        # Find where it ends (usually at Article 20)
        end_match = re.search(r"Artículo 2?0\.", text[start_pos:])
        end_pos = start_pos + end_match.start() if end_match else min(start_pos + 5000, len(text))
        
        content = text[start_pos:end_pos]
        
        # Strategy A: List format (e.g., Threshold 1: ...)
        list_found = False
        for i in range(1, 4):
            umbral_key = f"Umbral {i}"
            section_match = re.search(rf"{umbral_key}:(.*?)(?:Umbral {i+1}|Artículo 20|$)", content, re.DOTALL | re.IGNORECASE)
            if section_match:
                section_text = section_match.group(1)
                t_vals = {}
                # Extract members and their respective limits
                members_matches = re.finditer(r"Familias de ([a-z]+|\d+) miembros?:?\s*([\d\.,]+)\s*euros", section_text, re.IGNORECASE)
                for m in members_matches:
                    t_vals[m.group(1)] = m.group(2)
                if t_vals:
                     thresholds[umbral_key] = t_vals
                     list_found = True

        # Strategy B: Table format (harder to parse if lines get shifted)
        if not list_found:
            table_data = []
            lines = content.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # Check for "Row" format: Number (members) followed by 3 monetary amounts
                table_match = re.match(r"^(\d+)\s+([\d\.]+)\s+([\d\.]+)(?:\s+([\d\.]+))?", line)
                if table_match and int(table_match.group(1)) < 20: 
                     table_data.append({
                        "miembros": table_match.group(1),
                        "umbral_1": table_match.group(2),
                        "umbral_2": table_match.group(3),
                        "umbral_3": table_match.group(4) if table_match.group(4) else "N/A"
                    })
                     i += 1
                     continue

                # Sometimes tables are split line-by-line in the PDF
                if re.match(r"^\d+$", line) and int(line) < 20:
                    members = line
                    vals = []
                    lookahead = 1
                    while looks_like_amount(lines, i + lookahead):
                         vals.append(lines[i + lookahead].strip())
                         lookahead += 1
                         if len(vals) >= 3: break
                    
                    if len(vals) >= 2: 
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
        """Extracts thresholds for assets/wealth (Article 20)."""
        result = {}

        # Scan for Article 20 section
        match = re.search(r"Artículo 20\..*?Umbrales indicativos de patrimonio familiar\.(.*?)Artículo 21\.", text, re.DOTALL | re.IGNORECASE)
        if not match:
            match = re.search(r"umbrales indicativos de patrimonio familiar\.(.*?)(?:Artículo 21|CAPÍTULO)", text, re.DOTALL | re.IGNORECASE)

        if match:
            content = self.clean_text(match.group(1))

            # Urban properties limit
            urban = re.search(r"fincas urbanas.*?superar.*?([\d\.,]+)\s*euros", content, re.IGNORECASE)
            if urban:
                result["fincas_urbanas_limite"] = urban.group(1)

            # Rural constructions limit
            rural_const = re.search(r"construcciones situadas en fincas rústicas.*?superar.*?([\d\.,]+)\s*euros", content, re.IGNORECASE)
            if rural_const:
                result["construcciones_rusticas_limite"] = rural_const.group(1)

            # Rural land limit (per family member)
            rural_land = re.search(r"fincas rústicas excluidos.*?superar.*?([\d\.,]+)\s*euros.*?miembro", content, re.IGNORECASE)
            if rural_land:
                result["fincas_rusticas_limite_por_miembro"] = rural_land.group(1)

            # Financial capital limit (savings, etc.)
            capital = re.search(r"capital mobiliario.*?superar\s*([\d\.,]+)\s*euros", content, re.IGNORECASE)
            if capital:
                result["capital_mobiliario_limite"] = capital.group(1)

        return result if result else "No detectado"

    def extract_academic_requirements(self, text):
        """Extracts requirements like credit loads and pass rates."""
        result = {}

        # Minimum credits for full-time students
        credits_match = re.search(r"matriculados?.*?de\s+(\d+)\s+créditos.*?tiempo\s+completo", text, re.IGNORECASE | re.DOTALL)
        if credits_match:
            result["creditos_tiempo_completo"] = int(credits_match.group(1))

        # Minimum credits for partial enrollment
        partial_match = re.search(r"(?:matrícula parcial|matricularse de un mínimo de)\s*.*?(\d+)\s+créditos", text, re.IGNORECASE | re.DOTALL)
        if partial_match:
            result["creditos_matricula_parcial"] = int(partial_match.group(1))

        # Entry grade for new university students
        entry_match = re.search(r"requerirá.*?nota de\s+([\d,]+)\s+puntos.*?acceso", text, re.IGNORECASE | re.DOTALL)
        if entry_match:
            result["nota_acceso_universidad"] = entry_match.group(1)

        # Extraction of the percentage of credits that must be passed depending on the degree
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
        """Extracts the table mapping average grades to euro amounts."""
        brackets = []

        # We look for "Between X and Y points" patterns
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
        """Extracts extra aid for students from islands, Ceuta, or Melilla."""
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

        # Supplement for remote islands (like Lanzarote or Fuerteventura)
        remote = re.search(r"(?:adicional será de|adicional de)\s*([\d\.,]+)\s*euros.*?(?:Lanzarote|Fuerteventura)", content, flags)
        if not remote:
            remote = re.search(r"([\d\.,]+)\s*euros.*?(?:Lanzarote|Fuerteventura)", content, flags)
        if remote:
            result["suplemento_islas_remotas"] = remote.group(1)

        # Inter-island travel to the Mainland
        peninsula_amounts = re.findall(r"serán\s*(?:de\s*)?([\d\.,]+)\s*euros\s*y\s*([\d\.,]+)\s*euros", content, flags)
        if peninsula_amounts:
            result["suplemento_interinsular_peninsula"] = peninsula_amounts[0][0]
            result["suplemento_interinsular_peninsula_remotas"] = peninsula_amounts[0][1]

        # Extra for Canary Islands vocational training
        fp_extra = re.search(r"incrementarán en\s*([\d\.,]+)\s*euros", content, flags)
        if fp_extra:
            result["suplemento_fp_canarias"] = fp_extra.group(1)

        return result if result else "No detectado"

    def extract_income_deductions(self, text):
        """Extracts deductions that lower the calculated family income (e.g., disability)."""
        result = {}

        # Isolate the deductions section
        ded_match = re.search(r"deducciones siguientes:(.*?)(?:Artículo \d+\.|CAPÍTULO)", text, re.DOTALL | re.IGNORECASE)
        ded_text = ded_match.group(1) if ded_match else text

        flags = re.IGNORECASE | re.DOTALL

        # General large family
        familia_gral = re.search(r"(\d[\d\.,]*)\s*euros.*?familias numerosas de categoría general", ded_text, flags)
        if familia_gral:
            result["deduccion_familia_numerosa_general"] = familia_gral.group(1)

        # Special large family
        familia_esp = re.search(r"categoría general y\s*([\d\.,]+)\s*euros", ded_text, flags)
        if not familia_esp:
            familia_esp = re.search(r"([\d\.,]+)\s*euros.*?familias numerosas de categoría especial", ded_text, flags)
        if familia_esp:
            result["deduccion_familia_numerosa_especial"] = familia_esp.group(1)

        # Disability 33%-65%
        disc_33 = re.search(r"c\)\s*([\d\.,]+)\s*euros.*?discapacidad.*?treinta y tres", ded_text, flags)
        if disc_33:
            result["deduccion_discapacidad_33"] = disc_33.group(1)

        # Disability 65%+
        disc_65 = re.search(r"treinta y tres por\s*ciento\s*y\s*([\d\.,]+)\s*euros", ded_text, flags)
        if disc_65:
            result["deduccion_discapacidad_65"] = disc_65.group(1)

        # University applicant with 65%+ disability
        disc_uni = re.search(r"dicho solicitante\s*será\s*de\s*([\d\.,]+)\s*euros", ded_text, flags)
        if disc_uni:
            result["deduccion_discapacidad_65_universitario"] = disc_uni.group(1)

        # Sibling studying away from home
        hermano_fuera = re.search(r"d\)\s*([\d\.,]+)\s*euros.*?hermano.*?resida fuera", ded_text, flags)
        if hermano_fuera:
            result["deduccion_hermano_universitario_fuera"] = hermano_fuera.group(1)

        # Orphans (usually a percentage deduction)
        huerfano = re.search(r"e\)\s*(?:El\s*)?(\d+)\s*(?:%|por\s*ciento)", ded_text, flags)
        if huerfano:
            result["deduccion_huerfano_porcentaje"] = f"{huerfano.group(1)}%"

        # Single-parent families
        mono = re.search(r"f\)\s*([\d\.,]+)\s*euros.*?monoparental", ded_text, flags)
        if mono:
            result["deduccion_familia_monoparental"] = mono.group(1)

        return result if result else "No detectado"

    def extract_disability_provisions(self, text):
        """Extracts support measures for students with disabilities."""
        result = {}

        match = re.search(r"Artículo 13\..*?(?:discapacidad|Becas especiales)(.*?)Artículo 14\.", text, re.DOTALL | re.IGNORECASE)
        if not match:
            return "No detectado"

        content = self.clean_text(match.group(1))

        # Permission to reduce credit load
        if re.search(r"65 por\s*ciento.*?reducir.*?carga lectiva", content, re.IGNORECASE) or \
           re.search(r"discapacidad.*?65.*?reducir", content, re.IGNORECASE):
            result["reduccion_carga_lectiva"] = "Discapacidad >= 65%"

        # Fixed percentage increments
        incr_25 = re.search(r"incremento.*?(\d+) por\s*ciento.*?discapacidad.*?25.*?65", content, re.IGNORECASE)
        if not incr_25:
            incr_25 = re.search(r"(\d+) por\s*ciento.*?discapacidad igual o superior al 25", content, re.IGNORECASE)
        if incr_25:
            result["incremento_discapacidad_25_65"] = f"{incr_25.group(1)}%"

        incr_50 = re.search(r"incrementarán en un (\d+) por\s*ciento", content, re.IGNORECASE)
        if incr_50:
            result["incremento_matricula_completa_discapacidad"] = f"{incr_50.group(1)}%"

        return result if result else "No detectado"

    def extract_deadlines(self, text):
        """Extracts the application deadlines (dates)."""
        deadlines = {}
        
        # Look for the "Term" or "Deadline" section
        match = re.search(r"(?:Artículo \d+\.\s*)?(?:Lugar y )?Plazo de presentación de solicitudes\.(.*?)(?:Artículo|CAPÍTULO)", text, re.DOTALL | re.IGNORECASE)
        
        content = match.group(1) if match else ""
        if not content:
             match = re.search(r"plazos? para presentar la solicitud.*?(?=\. \d)", text, re.DOTALL | re.IGNORECASE)
             if match: content = match.group(0)

        if content:
            content_clean = self.clean_text(content)
            # Use regex to find dates format: "DD de month de YYYY"
            dates = re.findall(r"(\d{1,2} de \w+ de \d{4})", content_clean)
            deadlines["fechas_encontradas"] = dates
            
            # Specific deadlines for university vs non-university students
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
        """Main execution loop: finds PDFs, extracts data, and saves it."""
        if not self.ruta_data.exists():
            print(f"Error: Folder '{self.ruta_data}' doesn't exist.")
            return

        archivos_pdf = list(self.ruta_data.glob("*.pdf"))
        print(f"--- Starting processing of {len(archivos_pdf)} files ---")

        for ruta_pdf in archivos_pdf:
            print(f"Processing: {ruta_pdf.name}...")
            try:
                # We open the PDF and extract all text from all pages
                doc = fitz.open(ruta_pdf)
                texto_completo = "".join([pagina.get_text() for pagina in doc])
                
                # We build a large dictionary with all the extracted info
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
                print(f"Error reading {ruta_pdf.name}: {e}")

        self.guardar_resultados()

    def guardar_resultados(self):
        """Saves everything to JSON and CSV formats."""
        # Save to JSON (best for structured/nested data)
        with open("becas_estructuradas.json", "w", encoding="utf-8") as f:
            json.dump(self.datos_extraidos, f, indent=4, ensure_ascii=False)
        
        # Save to CSV (best for spreadsheets, but requires flattening nested dicts)
        if self.datos_extraidos:
            csv_data = []
            nested_fields = [
                "umbrales_renta", "umbrales_patrimonio", "requisitos_academicos",
                "excelencia_tramos", "suplementos_insulares", "deducciones_renta",
                "discapacidad", "plazos_solicitud"
            ]
            for item in self.datos_extraidos:
                row = item.copy()
                # For CSV, we convert internal dictionaries into JSON strings
                for field in nested_fields:
                    if field in row and isinstance(row[field], (dict, list)):
                        row[field] = json.dumps(row[field], ensure_ascii=False)
                # Trim long text to keep the CSV readable
                if len(row.get("programas_educativos", "")) > 500:
                    row["programas_educativos"] = row["programas_educativos"][:500] + "..."
                csv_data.append(row)

            columnas = csv_data[0].keys()
            with open("becas_estructuradas.csv", "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=columnas)
                writer.writeheader()
                writer.writerows(csv_data)
        
        print("\n--- Process Finished! ---")
        print("Generated files: 'becas_estructuradas.json' and 'becas_estructuradas.csv'")

def looks_like_amount(lines, idx):
    """Helper to check if a line of text looks like a currency amount (e.g., 10.500)."""
    if idx >= len(lines): return False
    return bool(re.match(r"^[\d\.]+$", lines[idx].strip()))

if __name__ == "__main__":
    # Start the system using the 'data' folder
    sistema = SistemaExtraccionBecas(carpeta_entrada="data")
    sistema.ejecutar()
