from livekit import api

token = api.AccessToken(api_key="APIB4tej5UNRWuB", api_secret="J9HeNaMZ8Iu6Zk1mRfCCSfqq29heJRwDvIsvVMgYxKqD").with_identity("priyangshu").with_name("Boss").with_grants(api.VideoGrants(room_join=True, room="ares-room")).to_jwt()

print(token)