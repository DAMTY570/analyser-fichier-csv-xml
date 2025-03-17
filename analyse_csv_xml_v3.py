import streamlit as st
import pandas as pd
import requests
import chardet
import lxml.etree as ET
from io import StringIO
import re

# Configuration initiale de la page
st.set_page_config(page_title="Analyseur CSV/XML", layout="wide")

def detect_encoding(file_content):
    result = chardet.detect(file_content)
    return result['encoding'], result['confidence']

def detect_separator(file_content, encoding):
    first_lines = file_content.decode(encoding).split('\n', 5)[:5]
    first_lines = "".join(first_lines)
    separators = [',', ';', '\t', '|']
    counts = [first_lines.count(sep) for sep in separators]
    max_count = max(counts)
    return separators[counts.index(max_count)] if max_count > 0 else None

def parse_csv(file_content):
    encoding, _ = detect_encoding(file_content)
    separator = detect_separator(file_content, encoding)
    df = pd.read_csv(StringIO(file_content.decode(encoding)), sep=separator,dtype=str, low_memory=False)
    df.replace("", pd.NA, inplace=True)
    return df

def parse_google_sheets(url):
    url = re.sub(r'\?.*$', '', url)
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if not match:
        raise ValueError("URL Google Sheets invalide. Assurez-vous qu'elle est correcte.")
    file_id = match.group(1)
    sheet_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv"
    response = requests.get(sheet_url)
    response.raise_for_status()
    return parse_csv(response.content)

# Fonctions pour un parseur XML scalable

def element_to_dict(elem):
    d = {}
    for child in elem:
        d[ET.QName(child).localname] = str(child.text) if child.text is not None else pd.NA
    return d

def find_repeating_sibling_elements(root):
    children = list(root)
    if not children:
        return None
    freq = {}
    for child in children:
        freq[child.tag] = freq.get(child.tag, 0) + 1
    candidate = None
    candidate_count = 0
    for tag, count in freq.items():
        if count > candidate_count:
            candidate = tag
            candidate_count = count
    if candidate_count > 1:
        return root.findall(f"./{candidate}")
    for child in children:
        result = find_repeating_sibling_elements(child)
        if result is not None and len(result) > 1:
            return result
    return None

def parse_xml_scalable(file_content):
    try:
        tree = ET.fromstring(file_content)
    except ET.XMLSyntaxError as e:
        st.error(f"Erreur de syntaxe XML : {e}")
        return pd.DataFrame()
    
    repeating_elements = find_repeating_sibling_elements(tree)
    if repeating_elements is None or len(repeating_elements) == 0:
        st.warning("Aucun élément répétitif n'a été détecté dans le fichier XML.")
        return pd.DataFrame()
    data = [element_to_dict(elem) for elem in repeating_elements]
    return pd.DataFrame(data)

def parse_xml(file_content):
    return parse_xml_scalable(file_content)

def process_file():
    file_key = f"file_uploader_{st.session_state['reset_count']}"
    url_key = f"file_url_{st.session_state['reset_count']}"
    # Cas d'un fichier uploadé
    if file_key in st.session_state and st.session_state[file_key] is not None:
        file = st.session_state[file_key]
        file_content = file.read()
        filename = file.name.lower()
        if filename.endswith(".csv"):
            st.session_state["dataframe"] = parse_csv(file_content)
        elif filename.endswith(".xml"):
            st.session_state["dataframe"] = parse_xml(file_content)
        else:
            st.error("Format de fichier non supporté.")
    # Cas d'une URL
    elif url_key in st.session_state and st.session_state[url_key]:
        file_url = st.session_state[url_key].strip()
        try:
            response = requests.get(file_url)
            response.raise_for_status()
            file_content = response.content
            content_type = response.headers.get("Content-Type", "").lower()
            if file_url.endswith(".csv") or "csv" in content_type:
                st.session_state["dataframe"] = parse_csv(file_content)
            elif file_url.endswith(".xml") or "xml" in content_type:
                st.session_state["dataframe"] = parse_xml(file_content)
            else:
                # Tentative automatique : d'abord CSV, sinon XML
                try:
                    st.session_state["dataframe"] = parse_csv(file_content)
                except Exception as e:
                    try:
                        st.session_state["dataframe"] = parse_xml(file_content)
                    except Exception as e:
                        st.error("Format de fichier non supporté.")
        except requests.exceptions.RequestException as e:
            st.error(f"Erreur de téléchargement du fichier : {e}")

def filter_by_brand():
    df = st.session_state["dataframe"]
    if st.radio("Filtrer par marques ?", ["Non", "Oui"], key="filter_choice") == "Oui":
        brand_column = st.selectbox("Colonne des marques :", df.columns, key="brand_column")
        unique_brands = df[brand_column].fillna("(Valeurs manquantes)").unique()
        selected_brands = st.multiselect("Sélectionnez les marques :", unique_brands, key="selected_brands")
        if selected_brands:
            filtered_df = df[df[brand_column].isin([b for b in selected_brands if b != "(Valeurs manquantes)"])]
            if "(Valeurs manquantes)" in selected_brands:
                filtered_df = pd.concat([filtered_df, df[df[brand_column].isna()]])
            st.session_state["filtered_df"] = filtered_df
            st.session_state["filter_active"] = True
        else:
            st.session_state["filtered_df"] = df
            st.session_state["filter_active"] = False
        if st.button("Réinitialiser le filtre"):
            st.session_state["filter_active"] = False
            st.session_state["filtered_df"] = None

def analyze_dataframe(df, key):
    st.subheader("Informations générales")
    st.write(f"**Nombre de lignes :** {df.shape[0]}")
    st.write(f"**Nombre de colonnes :** {df.shape[1]}")
    
    with st.expander("Aperçu des données"):
        st.dataframe(df.head(), use_container_width=True)
    
    st.download_button(
        label="Télécharger le fichier complet",
        data=df.to_csv(index=False).encode('utf-8'),
        file_name="fichier_complet.csv",
        mime="text/csv",
        key=f"download_{key}"
    )
    
    with st.expander("Types de données"):
        st.dataframe(df.dtypes.reset_index().rename(columns={0: "Type", "index": "Colonne"}), use_container_width=True)
    
    with st.expander("Valeurs manquantes"):
        missing_values = df.isnull().sum()
        if missing_values.sum() > 0:
            st.dataframe(missing_values.reset_index().rename(columns={0: "Valeurs Manquantes", "index": "Colonne"}))
        else:
            st.write("✅ Aucune valeur manquante trouvée.")
    
    with st.expander("Doublons par colonne"):
        duplicate_counts = df.apply(lambda x: x.dropna().duplicated(keep='first').sum())
        if duplicate_counts.sum() > 0:
            st.dataframe(duplicate_counts.reset_index().rename(columns={0: "Doublons", "index": "Colonne"}))
        else:
            st.write("✅ Aucun doublon trouvé.")

def explore_column(df, tab_key):
    if df is None or df.empty:
        st.warning("Aucun fichier n'est chargé ou aucun enregistrement n'a été extrait.")
        return
    column_name = st.selectbox("Choisissez une colonne à explorer :", df.columns, key=f"column_selector_{tab_key}")
    if column_name:
        st.markdown(f"#### Analyse de la colonne **{column_name}**")
        st.write(f"**Type de données :** {df[column_name].dtype}")
        st.write(f"**Nombre de valeurs uniques :** {df[column_name].nunique()}")
        st.write(f"**Nombre de valeurs manquantes :** {df[column_name].isnull().sum()}")
        duplicated_values = df[column_name].value_counts().loc[lambda x: x > 1]
        if not duplicated_values.empty:
            st.write("**Valeurs en doublon et leurs occurrences :**")
            st.dataframe(duplicated_values.reset_index().rename(columns={"index": "Valeur", column_name: "Occurrences"}))
        else:
            st.write("✅ Aucun doublon trouvé.")

def reset_analysis():
    st.session_state["dataframe"] = None
    st.session_state["filtered_df"] = None
    st.session_state["filter_active"] = False
    st.session_state["reset_count"] += 1
    st.success("Analyse réinitialisée. Veuillez charger un nouveau fichier ou entrer une URL.")

def main():
    if "reset_count" not in st.session_state:
        st.session_state["reset_count"] = 0
    if "dataframe" not in st.session_state:
        st.session_state["dataframe"] = None
    if "filtered_df" not in st.session_state:
        st.session_state["filtered_df"] = None
    if "filter_active" not in st.session_state:
        st.session_state["filter_active"] = False

    st.sidebar.header("Chargement du fichier")
    if st.sidebar.button("Réinitialiser l'analyse"):
        reset_analysis()
    
    if st.session_state["dataframe"] is None:
        st.sidebar.file_uploader("Téléversez un fichier CSV ou XML", type=["csv", "xml", "txt"],
                                 key=f"file_uploader_{st.session_state['reset_count']}", on_change=process_file)
        st.sidebar.text_input("Ou entrez une URL", key=f"file_url_{st.session_state['reset_count']}", on_change=process_file)
        st.sidebar.info("Après avoir chargé un fichier ou saisi une URL, les résultats apparaîtront ici.")
    else:
        st.sidebar.success("Fichier chargé avec succès!")
    
    st.title("Analyseur de fichiers CSV et XML")
    st.markdown("Bienvenue dans l'outil d'analyse. Utilisez la barre latérale pour charger un fichier. Une fois le fichier chargé, vous pouvez explorer vos données via les onglets ci-dessous.")
    
    if st.session_state["dataframe"] is not None:
        tab1, tab2 = st.tabs(["Analyse Globale", "Analyse par Marque"])
        with tab1:
            analyze_dataframe(st.session_state["dataframe"], "global")
            explore_column(st.session_state["dataframe"], "global")
        with tab2:
            filter_by_brand()
            df_to_use = st.session_state.get("filtered_df") if st.session_state.get("filter_active", False) else st.session_state["dataframe"]
            analyze_dataframe(df_to_use, "filtered")
            explore_column(df_to_use, "filtered")

if __name__ == "__main__":
    main()
