SELECT DISTINCT c.name
FROM Customers AS c JOIN Orders AS o ON c.cid = o.cid 
JOIN OrderItems AS oi ON o.oid = oi.oid JOIN Products AS p ON oi.pid = p.pid WHERE p.category IN ('Electronics', 'Books');
