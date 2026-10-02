from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    print("Audio client connected")

    try:
        while True:
            audio_chunk = await websocket.receive_bytes()

            print(
                f"Received {len(audio_chunk)} bytes"
            )

    except WebSocketDisconnect:
        print("Audio client disconnected")