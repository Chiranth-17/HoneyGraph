#!/bin/sh
set -eu

auth_args="--username $MONGO_ROOT_USERNAME --password $MONGO_ROOT_PASSWORD --authenticationDatabase admin"

echo "Waiting for mongo1 to accept authenticated connections..."
until mongosh --host mongo1 --port 27017 $auth_args --quiet --eval "db.adminCommand({ ping: 1 }).ok" 2>/dev/null | grep -q 1; do
  sleep 2
done

echo "Initiating replica set rs0..."
mongosh --host mongo1 --port 27017 $auth_args --quiet --eval '
  try {
    rs.status();
    print("Replica set already initialized");
  } catch (error) {
    if (error.codeName !== "NotYetInitialized" && error.code !== 94) throw error;
    rs.initiate({
      _id: "rs0",
      members: [
        { _id: 0, host: "mongo1:27017", priority: 2 },
        { _id: 1, host: "mongo2:27017", priority: 1 },
        { _id: 2, host: "mongo3:27017", priority: 1 }
      ]
    });
  }
'

echo "Waiting for exactly one PRIMARY and two SECONDARY members..."
until mongosh --host mongo1 --port 27017 $auth_args --quiet --eval '
  const states = rs.status().members.map(member => member.stateStr);
  quit(states.filter(state => state === "PRIMARY").length === 1 &&
       states.filter(state => state === "SECONDARY").length === 2 ? 0 : 1);
'; do
  sleep 2
done

echo "Replica set rs0 is ready."

