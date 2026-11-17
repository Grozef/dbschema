-- Cas limites pour dbschema : chaque table porte le cas qu'elle teste dans son nom.
CREATE TABLE parent (id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, name VARCHAR(50) NOT NULL);

-- FK obligatoire -> parent 1 / enfant 0..N
CREATE TABLE child_mandatory (id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, parent_id BIGINT UNSIGNED NOT NULL,
  FOREIGN KEY (parent_id) REFERENCES parent(id));
-- FK facultative -> parent 0..1 / enfant 0..N
CREATE TABLE child_optional (id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, parent_id BIGINT UNSIGNED NULL,
  FOREIGN KEY (parent_id) REFERENCES parent(id));
-- 1:1 obligatoire -> parent 1 / enfant 0..1
CREATE TABLE one_to_one_mandatory (id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, parent_id BIGINT UNSIGNED NOT NULL UNIQUE,
  FOREIGN KEY (parent_id) REFERENCES parent(id));
-- 1:1 facultatif -> parent 0..1 / enfant 0..1
CREATE TABLE one_to_one_optional (id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, parent_id BIGINT UNSIGNED NULL UNIQUE,
  FOREIGN KEY (parent_id) REFERENCES parent(id));
-- auto-reference
CREATE TABLE self_ref (id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, manager_id BIGINT UNSIGNED NULL,
  FOREIGN KEY (manager_id) REFERENCES self_ref(id));
-- FK composite
CREATE TABLE composite_parent (a INT NOT NULL, b INT NOT NULL, label VARCHAR(20), PRIMARY KEY (a, b));
CREATE TABLE composite_child (id INT AUTO_INCREMENT PRIMARY KEY, a INT NOT NULL, b INT NOT NULL,
  FOREIGN KEY (a, b) REFERENCES composite_parent(a, b));
-- FK circulaire
CREATE TABLE circular_x (id INT AUTO_INCREMENT PRIMARY KEY, y_id INT NULL);
CREATE TABLE circular_y (id INT AUTO_INCREMENT PRIMARY KEY, x_id INT NOT NULL, FOREIGN KEY (x_id) REFERENCES circular_x(id));
ALTER TABLE circular_x ADD FOREIGN KEY (y_id) REFERENCES circular_y(id);
-- table isolee
CREATE TABLE isolated (id INT AUTO_INCREMENT PRIMARY KEY, note TEXT);
-- table hub : referencee par 9 tables (> 8 = seuil par defaut) -> liens en amorces
CREATE TABLE hub (id INT AUTO_INCREMENT PRIMARY KEY);
CREATE TABLE hub_ref_1 (id INT AUTO_INCREMENT PRIMARY KEY, hub_id INT NOT NULL, FOREIGN KEY (hub_id) REFERENCES hub(id));
CREATE TABLE hub_ref_2 (id INT AUTO_INCREMENT PRIMARY KEY, hub_id INT NOT NULL, FOREIGN KEY (hub_id) REFERENCES hub(id));
CREATE TABLE hub_ref_3 (id INT AUTO_INCREMENT PRIMARY KEY, hub_id INT NOT NULL, FOREIGN KEY (hub_id) REFERENCES hub(id));
CREATE TABLE hub_ref_4 (id INT AUTO_INCREMENT PRIMARY KEY, hub_id INT NOT NULL, FOREIGN KEY (hub_id) REFERENCES hub(id));
CREATE TABLE hub_ref_5 (id INT AUTO_INCREMENT PRIMARY KEY, hub_id INT NOT NULL, FOREIGN KEY (hub_id) REFERENCES hub(id));
CREATE TABLE hub_ref_6 (id INT AUTO_INCREMENT PRIMARY KEY, hub_id INT NOT NULL, FOREIGN KEY (hub_id) REFERENCES hub(id));
CREATE TABLE hub_ref_7 (id INT AUTO_INCREMENT PRIMARY KEY, hub_id INT NOT NULL, FOREIGN KEY (hub_id) REFERENCES hub(id));
CREATE TABLE hub_ref_8 (id INT AUTO_INCREMENT PRIMARY KEY, hub_id INT NOT NULL, FOREIGN KEY (hub_id) REFERENCES hub(id));
CREATE TABLE hub_ref_9 (id INT AUTO_INCREMENT PRIMARY KEY, hub_id INT NULL, FOREIGN KEY (hub_id) REFERENCES hub(id));

-- cle partagee 1:1 : la PK de profile est aussi une FK, et profile est referencee par profile_photo
CREATE TABLE profile (parent_id BIGINT UNSIGNED NOT NULL PRIMARY KEY, bio TEXT,
  FOREIGN KEY (parent_id) REFERENCES parent(id));
CREATE TABLE profile_photo (id INT AUTO_INCREMENT PRIMARY KEY, profile_id BIGINT UNSIGNED NOT NULL,
  FOREIGN KEY (profile_id) REFERENCES profile(parent_id));
-- FK vers une colonne UNIQUE qui n'est pas la PK (doit rester visible en mode cles : le lien y arrive)
CREATE TABLE country (id INT AUTO_INCREMENT PRIMARY KEY, iso CHAR(2) NOT NULL UNIQUE, label VARCHAR(50));
CREATE TABLE address (id INT AUTO_INCREMENT PRIMARY KEY, country_iso CHAR(2) NULL,
  FOREIGN KEY (country_iso) REFERENCES country(iso));
-- noms non latins : les largeurs de carte doivent venir de la mesure dans le navigateur
CREATE TABLE `catégorie_équipement` (id INT AUTO_INCREMENT PRIMARY KEY, `libellé_très_long_accentué` VARCHAR(80), `数据库名称` VARCHAR(20));
