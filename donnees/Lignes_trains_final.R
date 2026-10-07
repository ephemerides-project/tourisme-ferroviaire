##############################################################################@#######################################@#######################################@
# LIGNES FERROVIAIRES
#################################################################@#######################################@#######################################@

library(sf)
library(leaflet)
library(dplyr)

# ============================================================
# 1. Charger le GeoJSON
# ============================================================

trajets_grenoble_1h30 <- read.csv(
  "trajets_grenoble_1h30.csv",
  stringsAsFactors = FALSE
)

######### Avoir la longitude et latitude de la gare d'arrivée

trajets_grenoble_1h30 <- trajets_grenoble_1h30 %>%
  select(-any_of(c("lon_arrivee", "lat_arrivee"))) %>%
  left_join(
    gares %>%
      select(
        nom_gare,
        Latitude,
        Longitude
      ),
    by = c("Gare.d.arrivée" = "nom_gare")
  ) %>%
  rename(
    lon_arrivee = Longitude,
    lat_arrivee = Latitude
  )

trajets_carte <- trajets_grenoble_1h30 %>%
  filter(
    !is.na(lon_arrivee),
    !is.na(lat_arrivee),
    lon_arrivee >= -180,
    lon_arrivee <= 180,
    lat_arrivee >= -90,
    lat_arrivee <= 90
  )

lignes_train <- st_read(
  "Lignes.geojson",
  quiet = TRUE
)

# Vérification
print(st_geometry_type(lignes_train))
print(st_crs(lignes_train))

# Projection Leaflet
lignes_train <- st_transform(
  lignes_train,
  4326
)

# Garder uniquement les vraies lignes
lignes_train <- lignes_train %>%
  filter(
    st_geometry_type(geometry) %in%
      c("LINESTRING", "MULTILINESTRING")
  )

# ============================================================
# 2. Préparer les gares
# ============================================================

gares_arrivee_carte <- trajets_carte %>%
  st_drop_geometry() %>%
  distinct(
    Gare.d.arrivée,
    lon_arrivee,
    lat_arrivee
  ) %>%
  filter(
    !is.na(lon_arrivee),
    !is.na(lat_arrivee)
  )

# ============================================================
# 3. Carte
# ============================================================

leaflet() %>%
  
  addTiles() %>%
  
  # Lignes ferroviaires
  addPolylines(
    data = lignes_train,
    color = "red",
    weight = 3,
    opacity = 0.8
  ) %>%
  
  # Gare de Grenoble
  addCircleMarkers(
    lng = 5.714584,
    lat = 45.19149,
    radius = 8,
    color = "red",
    fillColor = "red",
    fillOpacity = 1,
    stroke = FALSE,
    popup = "Gare de Grenoble"
  ) %>%
  
  # Gares d'arrivée
  addCircleMarkers(
    data = gares_arrivee_carte,
    lng = ~lon_arrivee,
    lat = ~lat_arrivee,
    radius = 5,
    color = "blue",
    fillColor = "blue",
    fillOpacity = 0.9,
    stroke = FALSE,
    popup = ~paste0(
      "<b>", Gare.d.arrivée, "</b>"
    )
  ) %>%
  
  # Légende
  addLegend(
    position = "bottomright",
    colors = c("red", "black", "blue"),
    labels = c(
      "Gare de Grenoble",
      "Lignes ferroviaires",
      "Gares d'arrivée"
    ),
    title = "Réseau ferroviaire"
  ) %>%
  
  setView(
    lng = 5.714584,
    lat = 45.19149,
    zoom = 8
  )

