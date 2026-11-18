-- Noms et commentaires hostiles : ils doivent s'afficher tels quels dans le HTML, sans jamais s'executer.
CREATE TABLE `<img src=x onerror=alert(1)>` (
  id INT PRIMARY KEY,
  `"><svg onload=alert(2)>` VARCHAR(40) DEFAULT '</script><script>alert(3)</script>' COMMENT '<script>alert(4)</script>',
  lien VARCHAR(40) COMMENT 'javascript:alert(5)'
) COMMENT='</script><img src=x onerror=alert(6)>';
CREATE TABLE `<script>alert(7)</script>` (
  id INT PRIMARY KEY,
  parent_id INT NOT NULL COMMENT '&lt;b&gt; deja echappe',
  FOREIGN KEY (parent_id) REFERENCES `<img src=x onerror=alert(1)>` (id)
);
CREATE TABLE `__proto__` (id INT PRIMARY KEY, x INT, FOREIGN KEY (x) REFERENCES `<script>alert(7)</script>` (id));
