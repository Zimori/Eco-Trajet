-- Création des tables principales

drop schema if exists co2app cascade;
create schema co2app;
set search_path to co2app;

CREATE TABLE City (
    id INT PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE TransportMode (
    id INT PRIMARY KEY,
    co2_emission FLOAT,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE Route (
    id INT PRIMARY KEY,
    distance_km FLOAT,
    transport_mode_id INT,
    start_city_id INT,
    end_city_id INT,
    FOREIGN KEY (transport_mode_id) REFERENCES TransportMode(id),
    FOREIGN KEY (start_city_id) REFERENCES City(id),
    FOREIGN KEY (end_city_id) REFERENCES City(id)
);


CREATE TABLE Itinerary (
    id INT PRIMARY KEY,
    total_dist_km FLOAT,
    departure_city_id INT,
    arrival_city_id INT,
    FOREIGN KEY (departure_city_id) REFERENCES City(id),
    FOREIGN KEY (arrival_city_id) REFERENCES City(id)
);


CREATE TABLE _User (
    id INT PRIMARY KEY,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL
);

-- Relations n-n avec tables associatives

-- Un Itinerary peut contenir plusieurs Routes (et une Route peut appartenir à plusieurs Itineraries)
CREATE TABLE ItineraryRoute (
    itinerary_id INT,
    route_id INT,
    PRIMARY KEY (itinerary_id, route_id),
    FOREIGN KEY (itinerary_id) REFERENCES Itinerary(id),
    FOREIGN KEY (route_id) REFERENCES Route(id)
);

-- Un User peut "prendre" plusieurs Itineraries (et inversement)
CREATE TABLE UserItinerary (
    user_id INT,
    itinerary_id INT,
    PRIMARY KEY (user_id, itinerary_id),
    FOREIGN KEY (user_id) REFERENCES _User(id),
    FOREIGN KEY (itinerary_id) REFERENCES Itinerary(id)
);

-- DONNEES BRUTES 
-- Insertion des villes (source fiables : grandes villes d'Europe)
INSERT INTO City (id, name) VALUES
(1, 'Paris'),
(2, 'Lyon'),
(3, 'Marseille'),
(4, 'Berlin'),
(5, 'Amsterdam'),
(6, 'Madrid'),
(7, 'Rome'),
(8, 'Bruxelles');

-- Insertion des modes de transport (sources moyennes de CO2 g/km/passager)
-- Source indicative : ADEME, European Environment Agency
INSERT INTO TransportMode (id, name, co2_emission) VALUES
(1, 'Train', 14.0),
(2, 'Voiture', 120.0),
(3, 'Bus', 68.0),
(4, 'Avion', 285.0),
(5, 'Vélo', 0.0);

-- Insertion des routes
INSERT INTO Route (id, distance_km, transport_mode_id, start_city_id, end_city_id) VALUES
(1, 460, 1, 1, 2),   -- Paris -> Lyon en train
(2, 315, 2, 2, 3),   -- Lyon -> Marseille en voiture
(3, 1050, 4, 1, 4),  -- Paris -> Berlin en avion
(4, 650, 3, 5, 1),   -- Amsterdam -> Paris en bus
(5, 1270, 4, 6, 3),  -- Madrid -> Marseille en avion
(6, 1110, 1, 7, 1),  -- Rome -> Paris en train
(7, 320, 2, 1, 8),   -- Paris -> Bruxelles en voiture
(8, 900, 3, 8, 4);   -- Bruxelles -> Berlin en bus

-- Insertion des utilisateurs
INSERT INTO _User (id, first_name, last_name) VALUES
(1, 'Alice', 'Durand'),
(2, 'Bob', 'Martin'),
(3, 'Carla', 'Rossi'),
(4, 'David', 'Schmidt'),
(5, 'Eva', 'Lopez');

-- Insertion des itinéraires
INSERT INTO Itinerary (id, total_dist_km, departure_city_id, arrival_city_id) VALUES
(1, 775, 1, 3),     -- Paris → Marseille
(2, 1050, 1, 4),    -- Paris → Berlin
(3, 1270, 6, 3),    -- Madrid → Marseille
(4, 1110, 7, 1),    -- Rome → Paris
(5, 1220, 5, 4);    -- Amsterdam → Berlin

-- Liaison itinéraire → routes (ItineraryRoute)
INSERT INTO ItineraryRoute (itinerary_id, route_id) VALUES
(1, 1), (1, 2),     -- Paris → Lyon → Marseille
(2, 3),             -- Paris → Berlin
(3, 5),             -- Madrid → Marseille
(4, 6),             -- Rome → Paris
(5, 4), (5, 8);     -- Amsterdam → Paris → Berlin

-- Liaison utilisateur → itinéraires (UserItinerary)
INSERT INTO UserItinerary (user_id, itinerary_id) VALUES
(1, 1),
(2, 2),
(3, 3),
(4, 4),
(5, 5),
(1, 5),  -- Alice fait aussi Amsterdam → Berlin
(3, 1);  -- Carla fait aussi Paris → Marseille

