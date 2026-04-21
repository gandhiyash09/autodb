**DBMS COURSE PROJECT SQL COMMANDS:**



&#x20;CREATE TABLE query\_log (

&#x20;   ->     query\_id INT AUTO\_INCREMENT PRIMARY KEY,

&#x20;   ->     query\_text TEXT,

&#x20;   ->     execution\_time FLOAT,

&#x20;   ->     rows\_scanned INT,

&#x20;   ->     created\_at TIMESTAMP DEFAULT CURRENT\_TIMESTAMP

&#x20;   -> );



mysql> ALTER TABLE query\_log

&#x20;   -> ADD COLUMN query\_type VARCHAR(50),

&#x20;   -> ADD COLUMN used\_index BOOLEAN DEFAULT FALSE,

&#x20;   -> ADD COLUMN used\_mv BOOLEAN DEFAULT FALSE;



**stored procedure for query logged**

DELIMITER $$



CREATE PROCEDURE execute\_logged\_query(IN q TEXT)

BEGIN

&#x20;   DECLARE start\_time DOUBLE;

&#x20;   DECLARE end\_time DOUBLE;

&#x20;   DECLARE q\_type VARCHAR(20);

&#x20;   DECLARE rows\_examined INT DEFAULT 0;

&#x20;   DECLARE used\_idx BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE used\_mv BOOLEAN DEFAULT FALSE;



&#x20;   -- 🔹 Detect Query Type

&#x20;   SET q\_type =

&#x20;       CASE

&#x20;           WHEN q LIKE 'SELECT%' THEN 'SELECT'

&#x20;           WHEN q LIKE 'INSERT%' THEN 'INSERT'

&#x20;           WHEN q LIKE 'UPDATE%' THEN 'UPDATE'

&#x20;           WHEN q LIKE 'DELETE%' THEN 'DELETE'

&#x20;           ELSE 'OTHER'

&#x20;       END;



&#x20;   -- 🔹 Detect Index Usage (heuristic)

&#x20;   SET used\_idx =

&#x20;       CASE

&#x20;           WHEN q LIKE '%WHERE player\_id%' THEN TRUE

&#x20;           WHEN q LIKE '%WHERE match\_id%' THEN TRUE

&#x20;           WHEN q LIKE '%GROUP BY player\_id%' THEN TRUE

&#x20;           ELSE FALSE

&#x20;       END;



&#x20;   -- 🔹 Detect Materialized View Usage

&#x20;   SET used\_mv =

&#x20;       CASE

&#x20;           WHEN q LIKE '%player\_stats\_mv%' THEN TRUE

&#x20;           ELSE FALSE

&#x20;       END;



&#x20;   -- 🔹 Start Time (microsecond precision)

&#x20;   SET start\_time = UNIX\_TIMESTAMP(NOW(6));



&#x20;   -- 🔹 Execute Query

&#x20;   IF final\_plan = 'INDEX\_SCAN' THEN



&#x20;   SET @sql = REGEXP\_REPLACE(

&#x20;       q,

&#x20;       'match\_fact(?!\\\\w)',

&#x20;       'match\_fact FORCE INDEX(idx\_player)'

&#x20;   );



ELSE

&#x20;   SET @sql = q;

END IF;

&#x20;   PREPARE stmt FROM @sql;

&#x20;   EXECUTE stmt;

&#x20;   DEALLOCATE PREPARE stmt;



&#x20;   -- 🔹 End Time

&#x20;   SET end\_time = UNIX\_TIMESTAMP(NOW(6));



&#x20;   -- 🔹 Simulate Rows Examined (basic heuristic)

&#x20;   SET rows\_examined =

&#x20;       CASE

&#x20;           WHEN q LIKE '%match\_fact%' THEN 500

&#x20;           WHEN q LIKE '%player\_dim%' THEN 50

&#x20;           ELSE 100

&#x20;       END;



&#x20;   -- 🔹 Insert into Log Table

&#x20;   INSERT INTO query\_log (

&#x20;       query\_text,

&#x20;       execution\_time,

&#x20;       query\_type,

&#x20;       rows\_examined,

&#x20;       used\_index,

&#x20;       used\_mv

&#x20;   )

&#x20;   VALUES (

&#x20;       q,

&#x20;       end\_time - start\_time,

&#x20;       q\_type,

&#x20;       rows\_examined,

&#x20;       used\_idx,

&#x20;       used\_mv

&#x20;   );



END$$



DELIMITER ;





CREATE VIEW frequent\_queries AS

SELECT query\_text, COUNT(\*) AS frequency

FROM query\_log

GROUP BY query\_text

ORDER BY frequency DESC;



CREATE VIEW slow\_queries AS

SELECT query\_text, AVG(execution\_time) AS avg\_time

FROM query\_log

GROUP BY query\_text

ORDER BY avg\_time DESC;



CREATE VIEW heavy\_queries AS

SELECT fq.query\_text, fq.frequency, sq.avg\_time

FROM frequent\_queries fq

JOIN slow\_queries sq ON fq.query\_text = sq.query\_text

ORDER BY sq.avg\_time DESC;





**stored procedure for suggestion:**

DELIMITER $$



CREATE PROCEDURE suggest\_index()

BEGIN

&#x20;   SELECT

&#x20;       query\_text,

&#x20;       CASE

&#x20;           WHEN query\_text LIKE '%WHERE player\_id%'

&#x20;               THEN 'CREATE INDEX idx\_player ON match\_fact(player\_id);'

&#x20;           WHEN query\_text LIKE '%WHERE match\_id%'

&#x20;               THEN 'CREATE INDEX idx\_match ON match\_fact(match\_id);'

&#x20;           WHEN query\_text LIKE '%GROUP BY player\_id%'

&#x20;               THEN 'CREATE INDEX idx\_group\_player ON match\_fact(player\_id);'

&#x20;           ELSE 'No strong recommendation'

&#x20;       END AS recommendation

&#x20;   FROM heavy\_queries;

END$$



DELIMITER ;



**Materialized view**

CREATE TABLE player\_stats\_mv AS

SELECT player\_id, SUM(runs) AS total\_runs

FROM match\_fact

GROUP BY player\_id;



**Trigger:**

DELIMITER $$



CREATE TRIGGER update\_mv

AFTER INSERT ON match\_fact

FOR EACH ROW

BEGIN

&#x20;   INSERT INTO player\_stats\_mv (player\_id, total\_runs)

&#x20;   VALUES (NEW.player\_id, NEW.runs)

&#x20;   ON DUPLICATE KEY UPDATE total\_runs = total\_runs + NEW.runs;

END$$



DELIMITER ;





ALTER TABLE player\_stats\_mv ADD PRIMARY KEY (player\_id);



**smart query stored procedure**

DELIMITER $$



CREATE PROCEDURE smart\_player\_query()

BEGIN

&#x20;   DECLARE use\_mv BOOLEAN;



&#x20;   SELECT COUNT(\*) > 3 INTO use\_mv

&#x20;   FROM query\_log

&#x20;   WHERE query\_text LIKE '%SUM(runs)%';



&#x20;   IF use\_mv THEN

&#x20;       SELECT \* FROM player\_stats\_mv;

&#x20;   ELSE

&#x20;       SELECT player\_id, SUM(runs)

&#x20;       FROM match\_fact

&#x20;       GROUP BY player\_id;

&#x20;   END IF;

END$$



DELIMITER ;



**performance view**

CREATE VIEW query\_performance AS

SELECT

&#x20;   query\_text,

&#x20;   COUNT(\*) AS executions,

&#x20;   AVG(execution\_time) AS avg\_time

FROM query\_log

GROUP BY query\_text;







ALTER TABLE query\_log

ADD COLUMN estimated\_cost DOUBLE,

ADD COLUMN plan\_choice VARCHAR(50);



**helper procedure**

DELIMITER $$



CREATE PROCEDURE get\_query\_cost(IN q TEXT, OUT cost DOUBLE)

BEGIN

&#x20;   SET @explain\_query = CONCAT('EXPLAIN FORMAT=JSON ', q);



&#x20;   PREPARE stmt FROM @explain\_query;

&#x20;   EXECUTE stmt;

&#x20;   DEALLOCATE PREPARE stmt;



&#x20;   SET cost =

&#x20;       CASE

&#x20;           WHEN q LIKE '%GROUP BY%' THEN 100

&#x20;           WHEN q LIKE '%JOIN%' THEN 200

&#x20;           ELSE 50

&#x20;       END;

END$$



DELIMITER ;





**workload stats view**

CREATE VIEW workload\_stats AS

SELECT

&#x20;   query\_text,

&#x20;   COUNT(\*) AS frequency,

&#x20;   AVG(execution\_time) AS avg\_time,

&#x20;   AVG(rows\_examined) AS avg\_rows,

&#x20;   AVG(estimated\_cost) AS avg\_cost

FROM query\_log

GROUP BY query\_text;



**classify queries view**

CREATE VIEW query\_classification AS

SELECT \*,

&#x20;   CASE

&#x20;       WHEN avg\_cost > 150 THEN 'HIGH\_COST'

&#x20;       WHEN avg\_time > 0.01 THEN 'SLOW'

&#x20;       WHEN frequency > 5 THEN 'FREQUENT'

&#x20;       ELSE 'NORMAL'

&#x20;   END AS category

FROM workload\_stats;



**optimized execute**

DELIMITER $$



CREATE PROCEDURE optimized\_execute(IN q TEXT)

BEGIN

&#x20;   DECLARE plan VARCHAR(50);

&#x20;   DECLARE cost DOUBLE DEFAULT 0;

&#x20;   DECLARE use\_mv BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE use\_index BOOLEAN DEFAULT FALSE;



&#x20;   -- 🔹 Step 1: Estimate Cost

&#x20;   CALL get\_query\_cost(q, cost);



&#x20;   -- 🔹 Step 2: Decide Plan

&#x20;   IF cost > 150 AND q LIKE '%SUM(runs)%' THEN

&#x20;       SET plan = 'USE\_MATERIALIZED\_VIEW';

&#x20;       SET use\_mv = TRUE;



&#x20;       -- Execute optimized version

&#x20;       SELECT \* FROM player\_stats\_mv;



&#x20;   ELSEIF q LIKE '%WHERE player\_id%' THEN

&#x20;       SET plan = 'USE\_INDEX';

&#x20;       SET use\_index = TRUE;



&#x20;       SET @sql = q;

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;



&#x20;   ELSE

&#x20;       SET plan = 'FULL\_SCAN';



&#x20;       SET @sql = q;

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;

&#x20;   END IF;



&#x20;   -- 🔹 Step 3: Log execution (reuse your procedure logic)

&#x20;   INSERT INTO query\_log (

&#x20;       query\_text,

&#x20;       execution\_time,

&#x20;       estimated\_cost,

&#x20;       plan\_choice,

&#x20;       used\_index,

&#x20;       used\_mv

&#x20;   )

&#x20;   VALUES (

&#x20;       q,

&#x20;       0.001,  -- placeholder (can reuse timer)

&#x20;       cost,

&#x20;       plan,

&#x20;       use\_index,

&#x20;       use\_mv

&#x20;   );



END$$



DELIMITER ;



**index\_candidates:**

CREATE VIEW index\_candidates AS

SELECT

&#x20;   query\_text,

&#x20;   frequency,

&#x20;   avg\_time,

&#x20;   CASE

&#x20;       WHEN query\_text LIKE '%WHERE player\_id%' AND avg\_time > 0.005

&#x20;           THEN 'CREATE INDEX idx\_player ON match\_fact(player\_id)'

&#x20;       WHEN query\_text LIKE '%GROUP BY player\_id%' AND frequency > 5

&#x20;           THEN 'CREATE INDEX idx\_group\_player ON match\_fact(player\_id)'

&#x20;       ELSE 'LOW\_PRIORITY'

&#x20;   END AS recommendation

FROM workload\_stats;



**reusable queries**

CREATE VIEW mv\_candidates AS

SELECT

&#x20;   query\_text,

&#x20;   frequency,

&#x20;   avg\_cost

FROM workload\_stats

WHERE query\_text LIKE '%SUM(runs)%'

AND frequency > 3;



**get\_query\_cost procedure (updated)**

DELIMITER $$



DROP PROCEDURE IF EXISTS get\_query\_cost $$



CREATE PROCEDURE get\_query\_cost(IN q TEXT, OUT cost DOUBLE)

BEGIN

&#x20;   SET cost = 0;



&#x20;   -- Base cost

&#x20;   SET cost = cost + 50;



&#x20;   -- JOIN cost

&#x20;   IF q LIKE '%JOIN%' THEN

&#x20;       SET cost = cost + 150;

&#x20;   END IF;



&#x20;   -- GROUP BY cost

&#x20;   IF q LIKE '%GROUP BY%' THEN

&#x20;       SET cost = cost + 100;

&#x20;   END IF;



&#x20;   -- ORDER BY cost

&#x20;   IF q LIKE '%ORDER BY%' THEN

&#x20;       SET cost = cost + 80;

&#x20;   END IF;



&#x20;   -- WHERE filter (reduces cost slightly)

&#x20;   IF q LIKE '%WHERE%' THEN

&#x20;       SET cost = cost - 20;

&#x20;   END IF;



&#x20;   -- Subquery cost

&#x20;   IF q LIKE '%SELECT%SELECT%' THEN

&#x20;       SET cost = cost + 120;

&#x20;   END IF;



END$$



DELIMITER ;



**Queries for testing:**
CALL optimized\_execute('SELECT \* FROM match\_fact');

CALL optimized\_execute('SELECT \* FROM match\_fact WHERE player\_id = 1');

CALL optimized\_execute('SELECT player\_id, SUM(runs) FROM match\_fact GROUP BY player\_id');

CALL optimized\_execute('SELECT player\_id, SUM(runs) FROM match\_fact GROUP BY player\_id ORDER BY SUM(runs) DESC');

CALL optimized\_execute('SELECT p.player\_name, f.runs FROM match\_fact f JOIN player\_dim p ON f.player\_id = p.player\_id');

CALL optimized\_execute('SELECT p.player\_name, SUM(f.runs) FROM match\_fact f JOIN player\_dim p ON f.player\_id = p.player\_id GROUP BY p.player\_name');

CALL optimized\_execute('SELECT p.player\_name, f.runs FROM match\_fact f JOIN player\_dim p ON f.player\_id = p.player\_id WHERE f.player\_id = 1');

CALL optimized\_execute('SELECT \* FROM match\_fact WHERE runs > 30 AND wickets > 0');

CALL optimized\_execute('SELECT player\_id FROM match\_fact WHERE runs > (SELECT AVG(runs) FROM match\_fact)');

CALL optimized\_execute('SELECT player\_id, AVG(runs) FROM match\_fact GROUP BY player\_id HAVING AVG(runs) > 40');

CALL optimized\_execute('SELECT t.year, SUM(f.runs) FROM match\_fact f JOIN time\_dim t ON f.time\_id = t.time\_id GROUP BY t.year');

CALL optimized\_execute('SELECT p.player\_name, td.team\_name, SUM(f.runs)

FROM match\_fact f

JOIN player\_dim p ON f.player\_id = p.player\_id

JOIN team\_dim td ON f.team\_id = td.team\_id

GROUP BY p.player\_name, td.team\_name');

&#x20;CALL optimized\_execute('SELECT \* FROM player\_stats\_mv');

CALL optimized\_execute('SELECT \* FROM match\_fact ORDER BY runs DESC');

CALL optimized\_execute('SELECT p.player\_name, SUM(f.runs)

FROM match\_fact f

JOIN player\_dim p ON f.player\_id = p.player\_id

WHERE f.runs > 20

GROUP BY p.player\_name

ORDER BY SUM(f.runs) DESC');



**Analyzing the results**

SELECT \* FROM workload\_stats;

SELECT \* FROM query\_classification;

SELECT query\_text, estimated\_cost, plan\_choice

FROM query\_log;

SELECT \* FROM index\_candidates;



**Due to large width, we optimize the tables.**

CREATE TABLE query\_master (

&#x20;   query\_id INT AUTO\_INCREMENT PRIMARY KEY,

&#x20;   query\_text TEXT,

&#x20;   query\_hash VARCHAR(64) UNIQUE

);



**Foreign key constraints on query master:**

TRUNCATE TABLE query\_log;



ALTER TABLE query\_log

ADD CONSTRAINT fk\_query

FOREIGN KEY (query\_id) REFERENCES query\_master(query\_id);



**Updating optimized\_execute procedure:**
DELIMITER $$



CREATE PROCEDURE optimized\_execute(IN q TEXT)

BEGIN

&#x20;   DECLARE qid INT;

&#x20;   DECLARE cost DOUBLE DEFAULT 0;

&#x20;   DECLARE plan VARCHAR(50);

&#x20;   DECLARE use\_mv BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE use\_index BOOLEAN DEFAULT FALSE;



&#x20;   -- 🔹 Generate hash (simple version)

&#x20;   SET @hash = MD5(q);



&#x20;   -- 🔹 Insert into master if not exists

&#x20;   INSERT INTO query\_master (query\_text, query\_hash)

&#x20;   VALUES (q, @hash)

&#x20;   ON DUPLICATE KEY UPDATE query\_id = LAST\_INSERT\_ID(query\_id);



&#x20;   SET qid = LAST\_INSERT\_ID();



&#x20;   -- 🔹 Cost estimation

&#x20;   CALL get\_query\_cost(q, cost);



&#x20;   -- 🔹 Plan decision

&#x20;   IF cost > 150 AND q LIKE '%SUM(runs)%' THEN

&#x20;       SET plan = 'USE\_MV';

&#x20;       SET use\_mv = TRUE;

&#x20;       SELECT \* FROM player\_stats\_mv;



&#x20;   ELSEIF q LIKE '%WHERE player\_id%' THEN

&#x20;       SET plan = 'USE\_INDEX';

&#x20;       SET use\_index = TRUE;



&#x20;       SET @sql = q;

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;



&#x20;   ELSE

&#x20;       SET plan = 'FULL\_SCAN';



&#x20;       SET @sql = q;

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;

&#x20;   END IF;



&#x20;   -- 🔹 Log compactly

&#x20;   INSERT INTO query\_log (

&#x20;       query\_id,

&#x20;       execution\_time,

&#x20;       estimated\_cost,

&#x20;       plan\_choice,

&#x20;       used\_index,

&#x20;       used\_mv

&#x20;   )

&#x20;   VALUES (

&#x20;       qid,

&#x20;       0.001,

&#x20;       cost,

&#x20;       plan,

&#x20;       use\_index,

&#x20;       use\_mv

&#x20;   );



END$$



DELIMITER ;





**workload summary view**

CREATE VIEW workload\_summary AS

SELECT

&#x20;   q.query\_id,

&#x20;   LEFT(q.query\_text, 50) AS short\_query,

&#x20;   COUNT(\*) AS executions,

&#x20;   AVG(l.execution\_time) AS avg\_time,

&#x20;   AVG(l.estimated\_cost) AS avg\_cost

FROM query\_log l

JOIN query\_master q ON l.query\_id = q.query\_id

GROUP BY q.query\_id;



**optimizer\_view**

CREATE VIEW optimizer\_view AS

SELECT

&#x20;   q.query\_id,

&#x20;   LEFT(q.query\_text, 40) AS query\_preview,

&#x20;   l.plan\_choice,

&#x20;   l.used\_index,

&#x20;   l.used\_mv,

&#x20;   l.estimated\_cost

FROM query\_log l

JOIN query\_master q ON l.query\_id = q.query\_id;



**index\_suggestions**

CREATE VIEW index\_recommendation\_clean AS

SELECT

&#x20;   ws.query\_id,

&#x20;   ws.short\_query,

&#x20;   CASE

&#x20;       WHEN ws.short\_query LIKE '%player\_id%'

&#x20;           THEN 'INDEX(player\_id)'

&#x20;       WHEN ws.short\_query LIKE '%GROUP BY%'

&#x20;           THEN 'INDEX for aggregation'

&#x20;       ELSE 'LOW'

&#x20;   END AS suggestion

FROM workload\_summary ws;





**QUERY OPTIMIZATION BY STATISTICS:**



**column\_stats table:**

CREATE TABLE column\_stats (

&#x20;   table\_name VARCHAR(50),

&#x20;   column\_name VARCHAR(50),

&#x20;   total\_rows INT,

&#x20;   distinct\_values INT,

&#x20;   min\_value DOUBLE,

&#x20;   max\_value DOUBLE,

&#x20;   PRIMARY KEY (table\_name, column\_name)

);



**correlation stats**

CREATE TABLE correlation\_stats (

&#x20;   table\_name VARCHAR(50),

&#x20;   column1 VARCHAR(50),

&#x20;   column2 VARCHAR(50),

&#x20;   correlation DOUBLE,

&#x20;   PRIMARY KEY (table\_name, column1, column2)

);



**column stats collector**

DELIMITER $$



CREATE PROCEDURE collect\_column\_stats()

BEGIN

&#x20;   -- match\_fact: player\_id

&#x20;   INSERT INTO column\_stats

&#x20;   SELECT

&#x20;       'match\_fact',

&#x20;       'player\_id',

&#x20;       COUNT(\*),

&#x20;       COUNT(DISTINCT player\_id),

&#x20;       MIN(player\_id),

&#x20;       MAX(player\_id)

&#x20;   FROM match\_fact

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_rows = VALUES(total\_rows),

&#x20;       distinct\_values = VALUES(distinct\_values);



&#x20;   -- match\_fact: runs

&#x20;   INSERT INTO column\_stats

&#x20;   SELECT

&#x20;       'match\_fact',

&#x20;       'runs',

&#x20;       COUNT(\*),

&#x20;       COUNT(DISTINCT runs),

&#x20;       MIN(runs),

&#x20;       MAX(runs)

&#x20;   FROM match\_fact

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_rows = VALUES(total\_rows),

&#x20;       distinct\_values = VALUES(distinct\_values);

END$$



DELIMITER ;



CALL collect\_column\_stats();



**selectivity view stats**

CREATE VIEW selectivity\_stats AS

SELECT

&#x20;   table\_name,

&#x20;   column\_name,

&#x20;   distinct\_values / total\_rows AS selectivity

FROM column\_stats;



**correlation\_stats:**

INSERT INTO correlation\_stats

SELECT

&#x20;   'match\_fact',

&#x20;   'player\_id',

&#x20;   'runs',

&#x20;   CASE

&#x20;       WHEN STDDEV(player\_id) = 0 OR STDDEV(runs) = 0 THEN 0

&#x20;       ELSE

&#x20;           (AVG(player\_id \* runs) - AVG(player\_id) \* AVG(runs)) /

&#x20;           (STDDEV(player\_id) \* STDDEV(runs))

&#x20;   END

FROM match\_fact;



**updated get query cost procedure:**
DELIMITER $$



DROP PROCEDURE IF EXISTS get\_query\_cost $$



CREATE PROCEDURE get\_query\_cost(IN q TEXT, OUT cost DOUBLE)

BEGIN

&#x20;   DECLARE sel DOUBLE DEFAULT 1;



&#x20;   -- Base cost

&#x20;   SET cost = 50;



&#x20;   -- JOIN cost

&#x20;   IF q LIKE '%JOIN%' THEN

&#x20;       SET cost = cost + 200;

&#x20;   END IF;



&#x20;   -- GROUP BY cost

&#x20;   IF q LIKE '%GROUP BY%' THEN

&#x20;       SET cost = cost + 120;

&#x20;   END IF;



&#x20;   -- ORDER BY cost

&#x20;   IF q LIKE '%ORDER BY%' THEN

&#x20;       SET cost = cost + 80;

&#x20;   END IF;



&#x20;   -- SELECTIVITY-based reduction

&#x20;   IF q LIKE '%WHERE player\_id%' THEN

&#x20;       SELECT selectivity INTO sel

&#x20;       FROM selectivity\_stats

&#x20;       WHERE column\_name = 'player\_id'

&#x20;       LIMIT 1;



&#x20;       SET cost = cost \* sel;

&#x20;   END IF;



END$$



DELIMITER ;





**optimized execute**

DELIMITER $$



DROP PROCEDURE IF EXISTS optimized\_execute $$



CREATE PROCEDURE optimized\_execute(IN q TEXT)

BEGIN

&#x20;   DECLARE qid INT;

&#x20;   DECLARE cost DOUBLE DEFAULT 0;

&#x20;   DECLARE plan VARCHAR(50);

&#x20;   DECLARE use\_mv BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE use\_index BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE sel DOUBLE DEFAULT 1;



&#x20;   -- 🔹 Step 1: Store query in master

&#x20;   SET @hash = MD5(q);



&#x20;   INSERT INTO query\_master (query\_text, query\_hash)

&#x20;   VALUES (q, @hash)

&#x20;   ON DUPLICATE KEY UPDATE query\_id = LAST\_INSERT\_ID(query\_id);



&#x20;   SET qid = LAST\_INSERT\_ID();



&#x20;   -- 🔹 Step 2: Get cost (NEW LOGIC USED HERE)

&#x20;   CALL get\_query\_cost(q, cost);



&#x20;   -- 🔹 Step 3: Get selectivity (if filter exists)

&#x20;   IF q LIKE '%WHERE player\_id%' THEN

&#x20;       SELECT selectivity INTO sel

&#x20;       FROM selectivity\_stats

&#x20;       WHERE column\_name = 'player\_id'

&#x20;       LIMIT 1;

&#x20;   END IF;



&#x20;   -- 🔥 Step 4: COST-BASED PLAN DECISION



&#x20;   IF cost < 50 THEN

&#x20;       SET plan = 'INDEX\_SCAN';

&#x20;       SET use\_index = TRUE;



&#x20;   ELSEIF cost BETWEEN 50 AND 180 THEN

&#x20;       SET plan = 'PARTIAL\_SCAN';



&#x20;   ELSEIF cost > 180 AND q LIKE '%SUM(runs)%' THEN

&#x20;       SET plan = 'USE\_MV';

&#x20;       SET use\_mv = TRUE;



&#x20;   ELSE

&#x20;       SET plan = 'FULL\_SCAN';

&#x20;   END IF;



&#x20;   -- 🔹 Step 5: Execute based on plan



&#x20;   IF use\_mv THEN

&#x20;       SELECT \* FROM player\_stats\_mv;



&#x20;   ELSE

&#x20;       SET @sql = q;

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;

&#x20;   END IF;



&#x20;   -- 🔹 Step 6: Log



&#x20;   INSERT INTO query\_log (

&#x20;       query\_id,

&#x20;       execution\_time,

&#x20;       estimated\_cost,

&#x20;       plan\_choice,

&#x20;       used\_index,

&#x20;       used\_mv

&#x20;   )

&#x20;   VALUES (

&#x20;       qid,

&#x20;       0.001,

&#x20;       cost,

&#x20;       plan,

&#x20;       use\_index,

&#x20;       use\_mv

&#x20;   );



END$$



DELIMITER ;





**update collect\_column\_stats**

DELIMITER $$



DROP PROCEDURE IF EXISTS collect\_column\_stats $$



CREATE PROCEDURE collect\_column\_stats()

BEGIN



&#x20;   -- 🔹 match\_fact: player\_id

&#x20;   INSERT INTO column\_stats

&#x20;   SELECT

&#x20;       'match\_fact',

&#x20;       'player\_id',

&#x20;       COUNT(\*),

&#x20;       COUNT(DISTINCT player\_id),

&#x20;       MIN(player\_id),

&#x20;       MAX(player\_id)

&#x20;   FROM match\_fact

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_rows = VALUES(total\_rows),

&#x20;       distinct\_values = VALUES(distinct\_values),

&#x20;       min\_value = VALUES(min\_value),

&#x20;       max\_value = VALUES(max\_value);



&#x20;   -- 🔹 match\_fact: runs

&#x20;   INSERT INTO column\_stats

&#x20;   SELECT

&#x20;       'match\_fact',

&#x20;       'runs',

&#x20;       COUNT(\*),

&#x20;       COUNT(DISTINCT runs),

&#x20;       MIN(runs),

&#x20;       MAX(runs)

&#x20;   FROM match\_fact

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_rows = VALUES(total\_rows),

&#x20;       distinct\_values = VALUES(distinct\_values),

&#x20;       min\_value = VALUES(min\_value),

&#x20;       max\_value = VALUES(max\_value);



&#x20;   -- 🔹 match\_fact: match\_id

&#x20;   INSERT INTO column\_stats

&#x20;   SELECT

&#x20;       'match\_fact',

&#x20;       'match\_id',

&#x20;       COUNT(\*),

&#x20;       COUNT(DISTINCT match\_id),

&#x20;       MIN(match\_id),

&#x20;       MAX(match\_id)

&#x20;   FROM match\_fact

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_rows = VALUES(total\_rows),

&#x20;       distinct\_values = VALUES(distinct\_values),

&#x20;       min\_value = VALUES(min\_value),

&#x20;       max\_value = VALUES(max\_value);



&#x20;   -- 🔹 match\_fact: team\_id

&#x20;   INSERT INTO column\_stats

&#x20;   SELECT

&#x20;       'match\_fact',

&#x20;       'team\_id',

&#x20;       COUNT(\*),

&#x20;       COUNT(DISTINCT team\_id),

&#x20;       MIN(team\_id),

&#x20;       MAX(team\_id)

&#x20;   FROM match\_fact

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_rows = VALUES(total\_rows),

&#x20;       distinct\_values = VALUES(distinct\_values),

&#x20;       min\_value = VALUES(min\_value),

&#x20;       max\_value = VALUES(max\_value);



&#x20;   -- 🔹 match\_fact: time\_id

&#x20;   INSERT INTO column\_stats

&#x20;   SELECT

&#x20;       'match\_fact',

&#x20;       'time\_id',

&#x20;       COUNT(\*),

&#x20;       COUNT(DISTINCT time\_id),

&#x20;       MIN(time\_id),

&#x20;       MAX(time\_id)

&#x20;   FROM match\_fact

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_rows = VALUES(total\_rows),

&#x20;       distinct\_values = VALUES(distinct\_values),

&#x20;       min\_value = VALUES(min\_value),

&#x20;       max\_value = VALUES(max\_value);



END$$



DELIMITER ;



**collect all stats:**
DELIMITER $$



CREATE PROCEDURE collect\_all\_stats()

BEGIN

&#x20;   CALL collect\_column\_stats();



&#x20;   -- correlation

&#x20;   DELETE FROM correlation\_stats;



&#x20;   INSERT INTO correlation\_stats

&#x20;   SELECT

&#x20;       'match\_fact',

&#x20;       'player\_id',

&#x20;       'runs',

&#x20;       CASE

&#x20;           WHEN STDDEV(player\_id) = 0 OR STDDEV(runs) = 0 THEN 0

&#x20;           ELSE

&#x20;               (AVG(player\_id \* runs) - AVG(player\_id) \* AVG(runs)) /

&#x20;               (STDDEV(player\_id) \* STDDEV(runs))

&#x20;       END

&#x20;   FROM match\_fact;

END$$



DELIMITER ;



**update index\_candidates:**
CREATE OR REPLACE VIEW index\_candidates AS

SELECT

&#x20;   ws.query\_id,

&#x20;   ws.avg\_cost,

&#x20;   CASE

&#x20;       WHEN ws.avg\_cost > 150 AND ws.short\_query LIKE '%player\_id%'

&#x20;           THEN 'CREATE INDEX idx\_player ON match\_fact(player\_id)'

&#x20;       WHEN ws.avg\_cost > 200 AND ws.short\_query LIKE '%JOIN%'

&#x20;           THEN 'INDEX ON JOIN KEYS'

&#x20;       ELSE 'LOW\_PRIORITY'

&#x20;   END AS recommendation

FROM workload\_summary ws;



**update optimized execute**

DELIMITER $$



DROP PROCEDURE IF EXISTS optimized\_execute $$



CREATE PROCEDURE optimized\_execute(IN q TEXT)

BEGIN

&#x20;   DECLARE qid INT;

&#x20;   DECLARE cost DOUBLE DEFAULT 0;

&#x20;   DECLARE plan VARCHAR(50);

&#x20;   DECLARE use\_mv BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE use\_index BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE sel DOUBLE DEFAULT 1;

&#x20;   DECLARE corr DOUBLE DEFAULT 0;

&#x20;   DECLARE idx\_benefit DOUBLE DEFAULT 0;

&#x20;   -- 🔹 Step 1: Store query in master

&#x20;   SET @hash = MD5(q);



&#x20;   INSERT INTO query\_master (query\_text, query\_hash)

&#x20;   VALUES (q, @hash)

&#x20;   ON DUPLICATE KEY UPDATE query\_id = LAST\_INSERT\_ID(query\_id);



&#x20;   SET qid = LAST\_INSERT\_ID();



&#x20;   -- 🔹 Step 2: Get cost (NEW LOGIC USED HERE)

&#x20;   CALL get\_query\_cost(q, cost);



&#x20;   -- 🔹 Step 3: Get selectivity (if filter exists)

&#x20;   IF q LIKE '%WHERE player\_id%' THEN

&#x20;       SELECT selectivity INTO sel

&#x20;       FROM selectivity\_stats

&#x20;       WHERE column\_name = 'player\_id'

&#x20;       LIMIT 1;

&#x20;   END IF;



&#x20;   -- 🔥 Step 4: COST-BASED PLAN DECISION



&#x20;   -- better logic

\-- 🔹 get selectivity if filter

IF q LIKE '%WHERE player\_id%' THEN

&#x20;   SELECT selectivity INTO sel

&#x20;   FROM selectivity\_stats

&#x20;   WHERE column\_name = 'player\_id'

&#x20;   LIMIT 1;

END IF;



\-- 🔹 get correlation if applicable

IF q LIKE '%player\_id%' AND q LIKE '%runs%' THEN

&#x20;   SELECT correlation INTO corr

&#x20;   FROM correlation\_stats

&#x20;   WHERE column1 = 'player\_id' AND column2 = 'runs'

&#x20;   LIMIT 1;

END IF;



\-- 🔥 PLAN LOGIC



IF q LIKE '%WHERE%' AND sel < 0.1 THEN

&#x20;   SET plan = 'INDEX\_SCAN';

&#x20;   SET use\_index = TRUE;



ELSEIF q LIKE '%JOIN%' AND cost > 250 THEN

&#x20;   IF corr > 0.5 THEN

&#x20;       SET plan = 'MERGE\_JOIN\_SIM';

&#x20;   ELSE

&#x20;       SET plan = 'HASH\_JOIN\_SIM';

&#x20;   END IF;



ELSEIF q LIKE '%GROUP BY%' AND cost > 200 THEN

&#x20;   SET plan = 'AGGREGATE\_PUSHDOWN';



ELSEIF q LIKE '%SUM(runs)%' AND cost > 200 THEN

&#x20;   SET plan = 'USE\_MV';

&#x20;   SET use\_mv = TRUE;



ELSEIF cost > 350 THEN

&#x20;   SET plan = 'FULL\_TABLE\_SCAN';



ELSE

&#x20;   SET plan = 'PARTIAL\_SCAN';

END IF;    -- 🔹 Step 5: Execute based on plan



&#x20;   IF use\_mv THEN

&#x20;       SELECT \* FROM player\_stats\_mv;



&#x20;   ELSE

&#x20;       SET @sql = q;

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;

&#x20;   END IF;

&#x20;

&#x20;   SET idx\_benefit = cost \* (1 - sel);

&#x20;   -- 🔹 Step 6: Log



&#x20;   INSERT INTO query\_log (

&#x20;       query\_id,

&#x20;       execution\_time,

&#x20;       estimated\_cost,

&#x20;       plan\_choice,

&#x20;       used\_index,

&#x20;       used\_mv,

&#x20;       index\_benefit

&#x20;   )

&#x20;   VALUES (

&#x20;       qid,

&#x20;       0.001,

&#x20;       cost,

&#x20;       plan,

&#x20;       use\_index,

&#x20;       use\_mv,

&#x20;       idx\_benefit

&#x20;   );

&#x20;   INSERT INTO query\_feedback (query\_id, plan\_choice, avg\_execution\_time, avg\_cost, executions)

VALUES (qid, plan, 0.001, cost, 1)



ON DUPLICATE KEY UPDATE

&#x20;   executions = executions + 1,

&#x20;   avg\_execution\_time = (avg\_execution\_time \* executions + 0.001) / (executions + 1),

&#x20;   avg\_cost = (avg\_cost \* executions + cost) / (executions + 1);



END$$



DELIMITER ;



**index\_candidates:**
CREATE OR REPLACE VIEW index\_candidates AS

SELECT

&#x20;   ws.query\_id,

&#x20;   ws.executions,

&#x20;   ws.avg\_cost,



&#x20;   CASE



&#x20;       -- 🔥 HIGH IMPACT FILTER INDEX

&#x20;       WHEN ws.avg\_cost > 100

&#x20;            AND ws.executions >= 1

&#x20;            AND qm.query\_text LIKE '%WHERE player\_id%'

&#x20;       THEN 'CREATE INDEX idx\_player ON match\_fact(player\_id)'



&#x20;       -- 🔥 JOIN INDEXES

&#x20;       WHEN ws.avg\_cost > 200

&#x20;            AND qm.query\_text LIKE '%JOIN%'

&#x20;       THEN 'CREATE INDEX idx\_join\_keys ON match\_fact(player\_id, team\_id)'



&#x20;       -- 🔥 GROUP BY INDEX

&#x20;       WHEN ws.avg\_cost > 150

&#x20;            AND qm.query\_text LIKE '%GROUP BY player\_id%'

&#x20;       THEN 'CREATE INDEX idx\_group\_player ON match\_fact(player\_id)'



&#x20;       -- 🔥 ORDER BY OPTIMIZATION

&#x20;       WHEN ws.avg\_cost > 120

&#x20;            AND qm.query\_text LIKE '%ORDER BY runs%'

&#x20;       THEN 'CREATE INDEX idx\_runs ON match\_fact(runs)'



&#x20;       -- 🔥 COMPOSITE INDEX

&#x20;       WHEN ws.avg\_cost > 250

&#x20;            AND qm.query\_text LIKE '%WHERE%'

&#x20;            AND qm.query\_text LIKE '%JOIN%'

&#x20;       THEN 'CREATE INDEX idx\_composite ON match\_fact(player\_id, team\_id, runs)'



&#x20;       ELSE 'LOW\_PRIORITY'



&#x20;   END AS recommendation



FROM workload\_summary ws

JOIN query\_master qm ON ws.query\_id = qm.query\_id;





**ADAPTIVE**



**query\_feedback table:**

CREATE TABLE query\_feedback (

&#x20;   query\_id INT,

&#x20;   plan\_choice VARCHAR(50),

&#x20;   avg\_execution\_time DOUBLE,

&#x20;   avg\_cost DOUBLE,

&#x20;   executions INT,

&#x20;   PRIMARY KEY (query\_id, plan\_choice)

);



**optimized execute:**

DELIMITER $$



DROP PROCEDURE IF EXISTS optimized\_execute $$



CREATE PROCEDURE optimized\_execute(IN q TEXT)

BEGIN

&#x20;   DECLARE qid INT;

&#x20;   DECLARE cost DOUBLE DEFAULT 0;

&#x20;   DECLARE plan VARCHAR(50);

&#x20;   DECLARE best\_plan VARCHAR(50);

&#x20;   DECLARE use\_mv BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE use\_index BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE sel DOUBLE DEFAULT 1;

&#x20;   DECLARE exec\_time DOUBLE DEFAULT 0.001;

&#x20;   DECLARE idx\_benefit DOUBLE DEFAULT 0;



&#x20;   -- 🔹 Step 1: Register query

&#x20;   SET @hash = MD5(q);



&#x20;   INSERT INTO query\_master (query\_text, query\_hash)

&#x20;   VALUES (q, @hash)

&#x20;   ON DUPLICATE KEY UPDATE query\_id = LAST\_INSERT\_ID(query\_id);



&#x20;   SET qid = LAST\_INSERT\_ID();



&#x20;   -- 🔹 Step 2: Get cost (from your advanced model)

&#x20;   CALL get\_query\_cost(q, cost);



&#x20;   -- 🔹 Step 3: Get selectivity (if applicable)

&#x20;   IF q LIKE '%WHERE player\_id%' THEN

&#x20;       SELECT selectivity INTO sel

&#x20;       FROM selectivity\_stats

&#x20;       WHERE column\_name = 'player\_id'

&#x20;       LIMIT 1;

&#x20;   END IF;



&#x20;   -- 🔹 Step 4: Compute index benefit

&#x20;   SET idx\_benefit = cost \* (1 - sel);



&#x20;   -- 🔥 Step 5: ADAPTIVE PLAN SELECTION



&#x20;   -- Try to learn from past executions

&#x20;   SELECT plan\_choice INTO best\_plan

&#x20;   FROM query\_feedback

&#x20;   WHERE query\_id = qid

&#x20;   ORDER BY avg\_execution\_time ASC

&#x20;   LIMIT 1;



&#x20;   IF best\_plan IS NOT NULL THEN

&#x20;       SET plan = best\_plan;



&#x20;   ELSE

&#x20;       -- fallback: cost-based logic

&#x20;       IF q LIKE '%WHERE%' AND sel < 0.1 THEN

&#x20;           SET plan = 'INDEX\_SCAN';

&#x20;           SET use\_index = TRUE;



&#x20;       ELSEIF q LIKE '%JOIN%' AND cost > 250 THEN

&#x20;           SET plan = 'HASH\_JOIN\_SIM';



&#x20;       ELSEIF q LIKE '%GROUP BY%' AND cost > 200 THEN

&#x20;           SET plan = 'AGGREGATE\_PUSHDOWN';



&#x20;       ELSEIF q LIKE '%SUM(runs)%' AND cost > 200 THEN

&#x20;           SET plan = 'USE\_MV';

&#x20;           SET use\_mv = TRUE;



&#x20;       ELSEIF cost > 350 THEN

&#x20;           SET plan = 'FULL\_TABLE\_SCAN';



&#x20;       ELSE

&#x20;           SET plan = 'PARTIAL\_SCAN';

&#x20;       END IF;

&#x20;   END IF;



&#x20;   -- 🔹 Step 6: EXECUTION



&#x20;   IF plan = 'USE\_MV' THEN

&#x20;       SELECT \* FROM player\_stats\_mv;



&#x20;   ELSEIF plan = 'INDEX\_SCAN' THEN

&#x20;       SET @sql = REPLACE(q, 'match\_fact', 'match\_fact FORCE INDEX(idx\_player)');

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;



&#x20;   ELSE

&#x20;       SET @sql = q;

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;

&#x20;   END IF;



&#x20;   -- 🔹 Step 7: LOG execution



&#x20;   INSERT INTO query\_log (

&#x20;       query\_id,

&#x20;       execution\_time,

&#x20;       estimated\_cost,

&#x20;       plan\_choice,

&#x20;       used\_index,

&#x20;       used\_mv,

&#x20;       index\_benefit

&#x20;   )

&#x20;   VALUES (

&#x20;       qid,

&#x20;       exec\_time,

&#x20;       cost,

&#x20;       plan,

&#x20;       use\_index,

&#x20;       use\_mv,

&#x20;       idx\_benefit

&#x20;   );



&#x20;   -- 🔥 Step 8: UPDATE LEARNING (ADAPTIVE FEEDBACK)



&#x20;   INSERT INTO query\_feedback (

&#x20;       query\_id,

&#x20;       plan\_choice,

&#x20;       avg\_execution\_time,

&#x20;       avg\_cost,

&#x20;       executions

&#x20;   )

&#x20;   VALUES (

&#x20;       qid,

&#x20;       plan,

&#x20;       exec\_time,

&#x20;       cost,

&#x20;       1

&#x20;   )

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       executions = executions + 1,

&#x20;       avg\_execution\_time =

&#x20;           (avg\_execution\_time \* executions + exec\_time) / (executions + 1),

&#x20;       avg\_cost =

&#x20;           (avg\_cost \* executions + cost) / (executions + 1);



END$$



DELIMITER ;



**optimize\_execute:**

DELIMITER $$



DROP PROCEDURE IF EXISTS optimized\_execute $$



CREATE PROCEDURE optimized\_execute(IN q TEXT)

BEGIN

&#x20;   DECLARE qid INT;

&#x20;   DECLARE cost DOUBLE DEFAULT 0;

&#x20;   DECLARE plan VARCHAR(50);

&#x20;   DECLARE best\_plan VARCHAR(50);

&#x20;   DECLARE use\_mv BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE use\_index BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE sel DOUBLE DEFAULT 1;

&#x20;   DECLARE exec\_time DOUBLE DEFAULT 0;

&#x20;   DECLARE idx\_benefit DOUBLE DEFAULT 0;

&#x20;   DECLARE query\_type VARCHAR(50);

&#x20;   DECLARE mv\_fresh BOOLEAN DEFAULT FALSE;

&#x20;   DECLARE best\_mv VARCHAR(50);



&#x20;   -- 🔹 Step 1: Register query

&#x20;   SET @hash = MD5(q);



&#x20;   INSERT INTO query\_master (query\_text, query\_hash)

&#x20;   VALUES (q, @hash)

&#x20;   ON DUPLICATE KEY UPDATE query\_id = LAST\_INSERT\_ID(query\_id);



&#x20;   SET qid = LAST\_INSERT\_ID();



&#x20;   -- 🔹 Step 2: Cost

&#x20;   CALL get\_query\_cost(q, cost);



&#x20;   -- 🔹 Step 3: Query type

&#x20;   IF q LIKE '%SUM(%' OR q LIKE '%GROUP BY%' THEN

&#x20;       SET query\_type = 'AGGREGATE';

&#x20;   ELSEIF q LIKE '%JOIN%' THEN

&#x20;       SET query\_type = 'JOIN';

&#x20;   ELSEIF q LIKE '%WHERE%' THEN

&#x20;       SET query\_type = 'FILTER';

&#x20;   ELSE

&#x20;       SET query\_type = 'SIMPLE';

&#x20;   END IF;



&#x20;   -- 🔹 Step 4: Selectivity

&#x20;   IF q LIKE '%WHERE player\_id%' THEN

&#x20;       SELECT selectivity INTO sel

&#x20;       FROM selectivity\_stats

&#x20;       WHERE column\_name = 'player\_id'

&#x20;       LIMIT 1;

&#x20;   END IF;



&#x20;   SET idx\_benefit = cost \* (1 - sel);



&#x20;   -- 🔥 Step 5: LEARNING FIRST

&#x20;   SELECT plan\_choice INTO best\_plan

&#x20;   FROM query\_feedback

&#x20;   WHERE query\_id = qid

&#x20;     AND query\_type = query\_type

&#x20;   ORDER BY avg\_execution\_time ASC

&#x20;   LIMIT 1;



&#x20;   IF best\_plan IS NOT NULL THEN

&#x20;       SET plan = best\_plan;



&#x20;   ELSE

&#x20;       -- 🔥 NEW: QUERY REWRITING USING MV (MOST IMPORTANT ADDITION)



&#x20;       -- Case: GROUP BY player\_id + WHERE player\_id

&#x20;       IF q LIKE '%GROUP BY player\_id%' AND q LIKE '%WHERE player\_id%' THEN



&#x20;           SELECT NOT is\_stale INTO mv\_fresh

&#x20;           FROM mv\_metadata

&#x20;           WHERE mv\_name = 'player\_stats\_mv'

&#x20;           LIMIT 1;



&#x20;           IF mv\_fresh THEN

&#x20;               SET plan = 'REWRITE\_USING\_PLAYER\_MV';

&#x20;               SET use\_mv = TRUE;

&#x20;           END IF;



&#x20;       END IF;



&#x20;       -- 🔹 Normal MV usage (existing)

&#x20;       IF plan IS NULL AND q LIKE '%GROUP BY player\_id%' THEN

&#x20;           SELECT NOT is\_stale INTO mv\_fresh

&#x20;           FROM mv\_metadata

&#x20;           WHERE mv\_name = 'player\_stats\_mv'

&#x20;           LIMIT 1;



&#x20;           IF mv\_fresh AND cost > 150 THEN

&#x20;               SET plan = 'USE\_MV';

&#x20;               SET use\_mv = TRUE;

&#x20;           END IF;

&#x20;       END IF;



&#x20;       IF plan IS NULL AND q LIKE '%GROUP BY player\_id, team\_id%' THEN

&#x20;           SELECT NOT is\_stale INTO mv\_fresh

&#x20;           FROM mv\_metadata

&#x20;           WHERE mv\_name = 'player\_team\_mv'

&#x20;           LIMIT 1;



&#x20;           IF mv\_fresh THEN

&#x20;               SET plan = 'USE\_PLAYER\_TEAM\_MV';

&#x20;               SET use\_mv = TRUE;

&#x20;           END IF;

&#x20;       END IF;



&#x20;       IF plan IS NULL AND q LIKE '%GROUP BY year%' THEN

&#x20;           SELECT NOT is\_stale INTO mv\_fresh

&#x20;           FROM mv\_metadata

&#x20;           WHERE mv\_name = 'yearly\_stats\_mv'

&#x20;           LIMIT 1;



&#x20;           IF mv\_fresh THEN

&#x20;               SET plan = 'USE\_YEARLY\_MV';

&#x20;               SET use\_mv = TRUE;

&#x20;           END IF;

&#x20;       END IF;



&#x20;       -- 🔹 Cost fallback

&#x20;       IF plan IS NULL THEN

&#x20;           IF query\_type = 'FILTER' AND sel < 0.1 THEN

&#x20;               SET plan = 'INDEX\_SCAN';

&#x20;               SET use\_index = TRUE;



&#x20;           ELSEIF query\_type = 'JOIN' AND cost > 250 THEN

&#x20;               SET plan = 'HASH\_JOIN\_SIM';



&#x20;           ELSEIF query\_type = 'AGGREGATE' AND cost > 200 THEN

&#x20;               SET plan = 'AGGREGATE\_PUSHDOWN';



&#x20;           ELSEIF cost > 350 THEN

&#x20;               SET plan = 'FULL\_TABLE\_SCAN';



&#x20;           ELSE

&#x20;               SET plan = 'PARTIAL\_SCAN';

&#x20;           END IF;

&#x20;       END IF;



&#x20;   END IF;



&#x20;   -- 🔥 Step 6: VALIDATION

&#x20;   IF plan = 'USE\_MV' AND q NOT LIKE '%SUM(runs)%' THEN

&#x20;       SET plan = NULL;

&#x20;   END IF;



&#x20;   IF plan IS NULL THEN

&#x20;       SET plan = 'FULL\_TABLE\_SCAN';

&#x20;   END IF;



&#x20;   -- 🔹 Step 7: EXECUTION

&#x20;   SET @start\_time = NOW(6);



&#x20;   -- 🔥 NEW EXECUTION: REWRITE USING MV

&#x20;   IF plan = 'REWRITE\_USING\_PLAYER\_MV' THEN



&#x20;       -- Extract player\_id (simple parsing)

&#x20;       SET @pid = SUBSTRING\_INDEX(q, '=', -1);



&#x20;       SET @sql = CONCAT(

&#x20;           'SELECT \* FROM player\_stats\_mv WHERE player\_id = ',

&#x20;           TRIM(@pid)

&#x20;       );



&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;



&#x20;       UPDATE mv\_metadata

&#x20;       SET usage\_count = usage\_count + 1

&#x20;       WHERE mv\_name = 'player\_stats\_mv';



&#x20;   ELSEIF plan = 'USE\_MV' THEN

&#x20;       SELECT \* FROM player\_stats\_mv;



&#x20;       UPDATE mv\_metadata

&#x20;       SET usage\_count = usage\_count + 1

&#x20;       WHERE mv\_name = 'player\_stats\_mv';



&#x20;   ELSEIF plan = 'USE\_PLAYER\_TEAM\_MV' THEN

&#x20;       SELECT \* FROM player\_team\_mv;



&#x20;   ELSEIF plan = 'USE\_YEARLY\_MV' THEN

&#x20;       SELECT \* FROM yearly\_stats\_mv;



&#x20;   ELSEIF plan = 'INDEX\_SCAN' THEN

&#x20;       SET @sql = REPLACE(q, 'match\_fact', 'match\_fact FORCE INDEX(idx\_player)');

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;



&#x20;   ELSE

&#x20;       SET @sql = q;

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;

&#x20;   END IF;



&#x20;   SET @end\_time = NOW(6);



&#x20;   SET exec\_time = ROUND(

&#x20;       TIMESTAMPDIFF(MICROSECOND, @start\_time, @end\_time) / 1000000,

&#x20;       6

&#x20;   );



&#x20;   -- 🔹 Step 8: LOG

&#x20;   INSERT INTO query\_log (

&#x20;       query\_id,

&#x20;       execution\_time,

&#x20;       estimated\_cost,

&#x20;       plan\_choice,

&#x20;       used\_index,

&#x20;       used\_mv,

&#x20;       index\_benefit

&#x20;   )

&#x20;   VALUES (

&#x20;       qid,

&#x20;       exec\_time,

&#x20;       cost,

&#x20;       plan,

&#x20;       use\_index,

&#x20;       use\_mv,

&#x20;       idx\_benefit

&#x20;   );



&#x20;   -- 🔥 Step 9: FEEDBACK

&#x20;   INSERT INTO query\_feedback (

&#x20;       query\_id,

&#x20;       plan\_choice,

&#x20;       query\_type,

&#x20;       avg\_execution\_time,

&#x20;       avg\_cost,

&#x20;       executions

&#x20;   )

&#x20;   VALUES (

&#x20;       qid,

&#x20;       plan,

&#x20;       query\_type,

&#x20;       exec\_time,

&#x20;       cost,

&#x20;       1

&#x20;   )

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       executions = executions + 1,

&#x20;       avg\_execution\_time =

&#x20;           (avg\_execution\_time \* executions + exec\_time) / (executions + 1),

&#x20;       avg\_cost =

&#x20;           (avg\_cost \* executions + cost) / (executions + 1);



END$$



DELIMITER ;



**learning\_progress:**

CREATE OR REPLACE VIEW learning\_progress\_short AS

SELECT

&#x20;   q.query\_id,

&#x20;   LEFT(qm.query\_text, 50) AS short\_query,

&#x20;   COUNT(\*) AS executions,

&#x20;   ROUND(AVG(q.execution\_time), 6) AS avg\_time

FROM query\_log q

JOIN query\_master qm ON q.query\_id = qm.query\_id

GROUP BY q.query\_id;



**evolution\_view:**
CREATE OR REPLACE VIEW plan\_evolution\_short AS

SELECT

&#x20;   q.query\_id,

&#x20;   LEFT(qm.query\_text, 40) AS short\_query,

&#x20;   q.plan\_choice,

&#x20;   COUNT(\*) AS times\_used,

&#x20;   ROUND(AVG(q.execution\_time), 6) AS avg\_time

FROM query\_log q

JOIN query\_master qm ON q.query\_id = qm.query\_id

GROUP BY q.query\_id, q.plan\_choice;



**learned\_best\_plan:**
CREATE OR REPLACE VIEW learned\_best\_plan AS

SELECT

&#x20;   qf.query\_id,

&#x20;   qm.query\_text,

&#x20;   qf.plan\_choice,

&#x20;   qf.avg\_execution\_time,

&#x20;   qf.executions

FROM query\_feedback qf

JOIN query\_master qm ON qf.query\_id = qm.query\_id

ORDER BY qf.avg\_execution\_time;



**WAREHOUSING CONCEPTS:**



**table date\_dim**

CREATE TABLE date\_dim (

&#x20;   date\_id INT PRIMARY KEY,

&#x20;   full\_date DATE,

&#x20;   year INT,

&#x20;   month INT,

&#x20;   day INT,

&#x20;   match\_season VARCHAR(10)

);



ALTER TABLE match\_fact ADD COLUMN date\_id INT;



**Player + team MV**

CREATE TABLE player\_team\_mv AS

SELECT

&#x20;   player\_id,

&#x20;   team\_id,

&#x20;   SUM(runs) AS total\_runs,

&#x20;   COUNT(\*) AS matches

FROM match\_fact

GROUP BY player\_id, team\_id;



**time-based mv**

CREATE TABLE yearly\_stats\_mv AS

SELECT

&#x20;   d.year,

&#x20;   SUM(f.runs) AS total\_runs

FROM match\_fact f

JOIN date\_dim d ON f.date\_id = d.date\_id

GROUP BY d.year;



**trigger-based update:**

DELIMITER $$



DROP TRIGGER IF EXISTS update\_player\_mv $$



CREATE TRIGGER update\_player\_mv

AFTER INSERT ON match\_fact

FOR EACH ROW

BEGIN

&#x20;   INSERT INTO player\_stats\_mv (player\_id, total\_runs)

&#x20;   VALUES (NEW.player\_id, NEW.runs)

&#x20;

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_runs = total\_runs + NEW.runs;

END$$



DELIMITER ;



**player\_team\_mv trigger**

DELIMITER $$



CREATE TRIGGER update\_player\_team\_mv

AFTER INSERT ON match\_fact

FOR EACH ROW

BEGIN

&#x20;   INSERT INTO player\_team\_mv (player\_id, team\_id, total\_runs, matches)

&#x20;   VALUES (NEW.player\_id, NEW.team\_id, NEW.runs, 1)



&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_runs = total\_runs + NEW.runs,

&#x20;       matches = matches + 1;

END$$



DELIMITER ;



**yearly\_stats\_mv trigger:**
DELIMITER $$



CREATE TRIGGER update\_yearly\_mv

AFTER INSERT ON match\_fact

FOR EACH ROW

BEGIN

&#x20;   DECLARE y INT;



&#x20;   SELECT year INTO y

&#x20;   FROM date\_dim

&#x20;   WHERE date\_id = NEW.date\_id;



&#x20;   INSERT INTO yearly\_stats\_mv (year, total\_runs)

&#x20;   VALUES (y, NEW.runs)



&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       total\_runs = total\_runs + NEW.runs;

END$$



DELIMITER ;





**WAREHOUSE OPTIMIZTION:**



**mv\_metadata table**

CREATE TABLE mv\_metadata (

&#x20;   mv\_name VARCHAR(50) PRIMARY KEY,

&#x20;   last\_updated TIMESTAMP,

&#x20;   usage\_count INT DEFAULT 0,

&#x20;   is\_stale BOOLEAN DEFAULT FALSE

);

INSERT INTO mv\_metadata (mv\_name, last\_updated)

VALUES

('player\_stats\_mv', NOW()),

('player\_team\_mv', NOW()),

('yearly\_stats\_mv', NOW());



**update trigger mv\_metadata:**
UPDATE mv\_metadata

SET last\_updated = NOW(), is\_stale = FALSE

WHERE mv\_name = 'player\_stats\_mv';





**TEST QUERRIES:**



CALL optimized\_execute('SELECT \* FROM match\_fact');

CALL optimized\_execute('SELECT \* FROM player\_dim');

CALL optimized\_execute('SELECT \* FROM team\_dim');

CALL optimized\_execute('SELECT \* FROM match\_fact WHERE player\_id = 1');

CALL optimized\_execute('SELECT \* FROM match\_fact WHERE player\_id = 2');

CALL optimized\_execute('SELECT \* FROM match\_fact WHERE runs > 50');

CALL optimized\_execute('SELECT \* FROM match\_fact WHERE team\_id = 3');

CALL optimized\_execute('

SELECT p.player\_name, f.runs

FROM match\_fact f

JOIN player\_dim p ON f.player\_id = p.player\_id');



CALL optimized\_execute('

SELECT p.player\_name, t.team\_name

FROM match\_fact f

JOIN player\_dim p ON f.player\_id = p.player\_id

JOIN team\_dim t ON f.team\_id = t.team\_id');

CALL optimized\_execute('SELECT player\_id, SUM(runs) FROM match\_fact GROUP BY player\_id');

CALL optimized\_execute('SELECT team\_id, SUM(runs) FROM match\_fact GROUP BY team\_id');

CALL optimized\_execute('SELECT player\_id, AVG(runs) FROM match\_fact GROUP BY player\_id');



CALL optimized\_execute('

SELECT player\_id, team\_id, SUM(runs)

FROM match\_fact

GROUP BY player\_id, team\_id');



CALL optimized\_execute('

SELECT team\_id, player\_id, SUM(runs)

FROM match\_fact

GROUP BY player\_id, team\_id');



CALL optimized\_execute('

SELECT d.year, SUM(f.runs)

FROM match\_fact f

JOIN date\_dim d ON f.date\_id = d.date\_id

GROUP BY d.year');



CALL optimized\_execute('

SELECT d.year, COUNT(\*)

FROM match\_fact f

JOIN date\_dim d ON f.date\_id = d.date\_id

GROUP BY d.year');



CALL optimized\_execute('

SELECT p.player\_name, SUM(f.runs)

FROM match\_fact f

JOIN player\_dim p ON f.player\_id = p.player\_id

WHERE f.runs > 20

GROUP BY p.player\_name');



CALL optimized\_execute('

SELECT p.player\_name, t.team\_name, SUM(f.runs)

FROM match\_fact f

JOIN player\_dim p ON f.player\_id = p.player\_id

JOIN team\_dim t ON f.team\_id = t.team\_id

GROUP BY p.player\_name, t.team\_name');



CALL optimized\_execute('

SELECT p.player\_name, SUM(f.runs)

FROM match\_fact f

JOIN player\_dim p ON f.player\_id = p.player\_id

GROUP BY p.player\_name

ORDER BY SUM(f.runs) DESC');



CALL optimized\_execute('SELECT \* FROM match\_fact ORDER BY runs DESC');

CALL optimized\_execute('SELECT \* FROM match\_fact ORDER BY player\_id');

CALL optimized\_execute('SELECT \* FROM match\_fact ORDER BY team\_id');



CALL optimized\_execute('

SELECT team\_id, COUNT(\*)

FROM match\_fact

WHERE runs > 30

GROUP BY team\_id');



CALL optimized\_execute('

SELECT player\_id, MAX(runs)

FROM match\_fact

GROUP BY player\_id');



CALL optimized\_execute('

SELECT player\_id, MIN(runs)

FROM match\_fact

GROUP BY player\_id');



SELECT \* FROM mv\_metadata;

SELECT \* FROM plan\_evolution\_short;



**Final modifications:**



DROP TABLE IF EXISTS yearly\_stats\_mv;



CREATE TABLE yearly\_stats\_mv AS

SELECT

&#x20;   d.year,

&#x20;   SUM(f.runs) AS total\_runs

FROM match\_fact f

JOIN date\_dim d ON f.date\_id = d.date\_id

GROUP BY d.year;



ALTER TABLE yearly\_stats\_mv

ADD PRIMARY KEY (year);



**Test after modifications:**

INSERT INTO match\_fact (match\_id, player\_id, team\_id, runs, date\_id)

SELECT

&#x20;   t1.id,

&#x20;   FLOOR(RAND()\*10)+1,

&#x20;   FLOOR(RAND()\*5)+1,

&#x20;   FLOOR(RAND()\*100),

&#x20;   101

FROM (

&#x20;   SELECT @row:=@row+1 AS id

&#x20;   FROM information\_schema.tables, (SELECT @row:=0) r

&#x20;   LIMIT 1000

) t1;





CREATE TABLE mv\_registry (

&#x20;   mv\_name VARCHAR(50),

&#x20;   base\_query TEXT,

&#x20;   pattern VARCHAR(100),

&#x20;   PRIMARY KEY (mv\_name)

);

INSERT INTO mv\_registry VALUES

('player\_stats\_mv', 'GROUP BY player\_id', 'AGGREGATE\_PLAYER'),

('player\_team\_mv', 'GROUP BY player\_id, team\_id', 'AGGREGATE\_PLAYER\_TEAM'),

('yearly\_stats\_mv', 'GROUP BY year', 'AGGREGATE\_YEAR');



**optimize execute:**

DELIMITER $$



DROP PROCEDURE IF EXISTS optimized\_execute $$



CREATE PROCEDURE optimized\_execute(IN q TEXT)

BEGIN

&#x20;   DECLARE qid INT;

&#x20;   DECLARE qtype VARCHAR(50);

&#x20;   DECLARE final\_plan VARCHAR(50);



&#x20;   DECLARE base\_cost DOUBLE DEFAULT 0;

&#x20;   DECLARE mv\_score DOUBLE DEFAULT 999999;

&#x20;   DECLARE idx\_score DOUBLE DEFAULT 999999;



&#x20;   DECLARE exec\_time DOUBLE DEFAULT 0;



&#x20;   DECLARE exec\_count INT DEFAULT 0; 

&#x20;   DECLARE avg\_cost DOUBLE DEFAULT 0; 



&#x20;   -- =====================================================

&#x20;   -- 1. NORMALIZATION

&#x20;   -- =====================================================

&#x20;   SET @qnorm = LOWER(TRIM(REPLACE(REPLACE(q, '\\n', ' '), '\\t', ' ')));



&#x20;   -- =====================================================

&#x20;   -- 2. FINGERPRINT (WORKLOAD IDENTIFIER)

&#x20;   -- =====================================================

&#x20;   SET @fingerprint =

&#x20;       MD5(

&#x20;           CASE

&#x20;               WHEN @qnorm LIKE '%group by player\_id%' AND @qnorm NOT LIKE '%team\_id%' THEN 'G1'

&#x20;               WHEN @qnorm LIKE '%group by player\_id, team\_id%' THEN 'G2'

&#x20;               WHEN @qnorm LIKE '%where player\_id%' THEN 'F1'

&#x20;               WHEN @qnorm LIKE '%join%' THEN 'J1'

&#x20;               ELSE 'S1'

&#x20;           END

&#x20;       );



&#x20;   -- =====================================================

&#x20;   -- 3. REGISTER QUERY

&#x20;   -- =====================================================

&#x20;   INSERT INTO query\_master(query\_text, query\_hash)

&#x20;   VALUES (q, @fingerprint)

&#x20;   ON DUPLICATE KEY UPDATE query\_id = LAST\_INSERT\_ID(query\_id);



&#x20;   SET qid = LAST\_INSERT\_ID();



&#x20;   IF qid IS NULL OR qid = 0 THEN

&#x20;       SET qid = FLOOR(RAND() \* 1000000);

&#x20;   END IF;



&#x20;   -- =====================================================

&#x20;   -- 4. CLASSIFICATION

&#x20;   -- =====================================================

&#x20;   IF @qnorm LIKE '%join%' THEN

&#x20;       SET qtype = 'JOIN';

&#x20;   ELSEIF @qnorm LIKE '%group by%' THEN

&#x20;       SET qtype = 'AGGREGATE';

&#x20;   ELSEIF @qnorm LIKE '%where%' THEN

&#x20;       SET qtype = 'FILTER';

&#x20;   ELSE

&#x20;       SET qtype = 'SIMPLE';

&#x20;   END IF;



&#x20;   -- =====================================================

&#x20;   -- 5. COST MODEL

&#x20;   -- =====================================================

&#x20;   CALL get\_query\_cost(q, base\_cost);



&#x20;   SET idx\_score =

&#x20;       CASE

&#x20;           WHEN qtype = 'FILTER' THEN base\_cost \* 0.4

&#x20;           WHEN qtype = 'JOIN' THEN base\_cost \* 0.7

&#x20;           ELSE base\_cost

&#x20;       END;



&#x20;   -- =====================================================

&#x20;   -- 6. LOAD WORKLOAD STATS

&#x20;   -- =====================================================

&#x20;   SELECT executions, avg\_cost

&#x20;   INTO exec\_count, avg\_cost 

&#x20;   FROM query\_feedback

&#x20;   WHERE query\_id = qid

&#x20;   LIMIT 1;



&#x20;   SET @exec\_count = IFNULL(@exec\_count, 0);

&#x20;   SET @avg\_cost = IFNULL(@avg\_cost, base\_cost);



&#x20;   -- =====================================================

&#x20;   -- 7. MV ELIGIBILITY (CRITICAL FIX)

&#x20;   -- =====================================================

&#x20;   SET @mv\_allowed = 0;



\-- STRICT BUT REALISTIC MV ELIGIBILITY

IF @qnorm LIKE '%group by player\_id%'

&#x20;  AND @qnorm LIKE '%sum(runs)%'

&#x20;  AND @qnorm NOT LIKE '%join match\_dim%'

THEN

&#x20;   SET @mv\_allowed = 1;

END IF;

&#x20;   -- =====================================================

&#x20;   -- 8. MV SCORE MODEL (WORKLOAD + COST)

&#x20;   -- =====================================================

&#x20;   IF @mv\_allowed = 1 THEN



&#x20;       IF @exec\_count >= 2 AND @avg\_cost > (base\_cost \* 0.6) THEN

&#x20;           SET mv\_score = (0.3 \* @avg\_cost) + (0.7 \* @exec\_count);

&#x20;       ELSE

&#x20;           SET mv\_score = base\_cost \* 0.6;

&#x20;       END IF;



&#x20;       -- pattern boost

&#x20;       IF @mv\_allowed = 1 THEN

&#x20;   SET mv\_score = LEAST(mv\_score, base\_cost \* 0.35);

ELSE

&#x20;   SET mv\_score = 999999;

END IF;



&#x20;   END IF;



&#x20;   -- =====================================================

&#x20;   -- 9. DECISION ENGINE

&#x20;   -- =====================================================

&#x20;   IF @mv\_allowed = 1

&#x20;      AND mv\_score < base\_cost

&#x20;      AND mv\_score < idx\_score THEN



&#x20;       SET final\_plan = 'USE\_MV';



&#x20;   ELSEIF idx\_score < base\_cost THEN

&#x20;       SET final\_plan = 'INDEX\_SCAN';



&#x20;   ELSE

&#x20;       SET final\_plan = 'FULL\_SCAN';

&#x20;   END IF;



&#x20;   -- safety

&#x20;   IF qtype != 'AGGREGATE' AND final\_plan = 'USE\_MV' THEN

&#x20;       SET final\_plan = 'FULL\_SCAN';

&#x20;   END IF;



&#x20;   -- =====================================================

&#x20;   -- 10. EXECUTION TIMER

&#x20;   -- =====================================================

&#x20;   SET @start = UNIX\_TIMESTAMP(NOW(6)) \* 1000000 + MICROSECOND(NOW(6));



&#x20;   IF final\_plan = 'USE\_MV' THEN



&#x20;       SELECT 'MV EXECUTION' AS plan\_used;

&#x20;       SELECT \* FROM player\_stats\_mv;



&#x20;   ELSEIF final\_plan = 'INDEX\_SCAN' THEN



&#x20;       SELECT 'INDEX EXECUTION' AS plan\_used;



&#x20;       SET @sql = REPLACE(q,

&#x20;           'match\_fact',

&#x20;           'match\_fact FORCE INDEX(idx\_player)'

&#x20;       );



&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;



&#x20;   ELSE



&#x20;       SELECT 'FULL SCAN EXECUTION' AS plan\_used;



&#x20;       SET @sql = q;

&#x20;       PREPARE stmt FROM @sql;

&#x20;       EXECUTE stmt;

&#x20;       DEALLOCATE PREPARE stmt;



&#x20;   END IF;



&#x20;   SET @end = UNIX\_TIMESTAMP(NOW(6)) \* 1000000 + MICROSECOND(NOW(6));



&#x20;   SET exec\_time = ROUND((@end - @start)/1000000, 6);



&#x20;   -- =====================================================

&#x20;   -- 11. LOGGING

&#x20;   -- =====================================================

&#x20;   INSERT INTO query\_log (

&#x20;       query\_id,

&#x20;       execution\_time,

&#x20;       estimated\_cost,

&#x20;       plan\_choice,

&#x20;       used\_index,

&#x20;       used\_mv,

&#x20;       index\_benefit

&#x20;   )

&#x20;   VALUES (

&#x20;       qid,

&#x20;       exec\_time,

&#x20;       base\_cost,

&#x20;       final\_plan,

&#x20;       IF(final\_plan='INDEX\_SCAN',1,0),

&#x20;       IF(final\_plan='USE\_MV',1,0),

&#x20;       ABS(base\_cost - idx\_score)

&#x20;   );



&#x20;   -- =====================================================

&#x20;   -- 12. WORKLOAD LEARNING

&#x20;   -- =====================================================

&#x20;   INSERT INTO workload\_stats (

&#x20;       fingerprint,

&#x20;       execution\_count,

&#x20;       avg\_time,

&#x20;       avg\_cost,

&#x20;       last\_plan

&#x20;   )

&#x20;   VALUES (

&#x20;       @fingerprint,

&#x20;       1,

&#x20;       exec\_time,

&#x20;       base\_cost,

&#x20;       final\_plan

&#x20;   )

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       execution\_count = execution\_count + 1,

&#x20;       avg\_time = (avg\_time \* execution\_count + VALUES(avg\_time)) / (execution\_count + 1),

&#x20;       avg\_cost = (avg\_cost \* execution\_count + VALUES(avg\_cost)) / (execution\_count + 1),

&#x20;       last\_plan = VALUES(last\_plan);



&#x20;   -- =====================================================

&#x20;   -- 13. FEEDBACK LEARNING

&#x20;   -- =====================================================

&#x20;   INSERT INTO query\_feedback(

&#x20;       query\_id,

&#x20;       plan\_choice,

&#x20;       avg\_execution\_time,

&#x20;       executions,

&#x20;       query\_type

&#x20;   )

&#x20;   VALUES (

&#x20;       qid,

&#x20;       final\_plan,

&#x20;       exec\_time,

&#x20;       1,

&#x20;       qtype

&#x20;   )

&#x20;   ON DUPLICATE KEY UPDATE

&#x20;       executions = executions + 1,

&#x20;       avg\_execution\_time =

&#x20;           (avg\_execution\_time \* executions + VALUES(avg\_execution\_time))

&#x20;           / (executions + 1);



END $$



DELIMITER ;



**Test Queries:**

CALL optimized\_execute('

SELECT match\_id, COUNT(\*), AVG(runs)

FROM match\_fact

GROUP BY match\_id

');	



CALL optimized\_execute('

SELECT player\_id, SUM(runs)

FROM match\_fact

WHERE runs BETWEEN 20 AND 50

GROUP BY player\_id

');



CALL optimized\_execute('

SELECT team\_id, AVG(runs), COUNT(\*)

FROM match\_fact

GROUP BY team\_id

');



**SELECT plan\_choice, COUNT(\*)** 

**FROM query\_log**

**GROUP BY plan\_choice;**



**SELECT plan\_choice,**

&#x20;      **ROUND(AVG(execution\_time), 6) AS avg\_time**

**FROM query\_log**

**GROUP BY plan\_choice;**



**SELECT fingerprint,**

&#x20;      **execution\_count,**

&#x20;      **avg\_time,**

&#x20;      **last\_plan**

**FROM workload\_stats;**



**SELECT \* FROM player\_stats\_mv;**



**SELECT query\_type,**

&#x20;      **COUNT(\*) as freq,**

&#x20;      **AVG(avg\_execution\_time) as mean\_time**

**FROM query\_feedback**

**GROUP BY query\_type;**



