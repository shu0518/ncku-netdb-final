SELECT DISTINCT P.name 
FROM Players P 
JOIN Teams T ON P.tid = T.tid 
WHERE NOT EXISTS (
    SELECT G.gid 
    FROM Games G 
    WHERE G.home_tid = T.tid 
    AND NOT EXISTS (
        SELECT Go.pid 
        FROM Goals Go 
        WHERE Go.gid = G.gid 
        AND Go.pid = P.pid
    )
);