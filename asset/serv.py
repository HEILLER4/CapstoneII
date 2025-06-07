from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/esp32/data', methods=['POST'])
def recieve_data():
	data = request.get_json(force=True)
	print("[recieved]", data)
	return jsonify({"status": "recieved"}), 200


if __name__ == "__main__":
	import os
	print("Running Flask on host:", os.environ.get("Flak run host"))
	print("should binfd to 0.0.0.0:8080")
	app.run(host="0.0.0.0",port=8080, debug=False)
