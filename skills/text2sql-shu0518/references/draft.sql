SELECT DISTINCT T1.name FROM Doctors AS T1 JOIN Departments AS T2 ON T1.did = T2.did WHERE T2.name = 'Cardiology'
UNION
SELECT DISTINCT T3.name FROM Patients AS T3 JOIN Appointments AS T4 ON T3.pid = T4.pid JOIN Doctors AS T5 ON T4.doc_id = T5.doc_id JOIN Departments AS T6 ON T5.did = T6.did WHERE T6.name = 'Cardiology'