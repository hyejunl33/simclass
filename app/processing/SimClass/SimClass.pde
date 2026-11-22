import java.net.HttpURLConnection;
import java.net.URL;
import java.io.OutputStream;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import processing.data.JSONArray;
import processing.data.JSONObject;

// SimClass — Processing client (MVP)
// Sends a teacher utterance to FastAPI and renders mock student responses.

final String SERVER_URL = "http://127.0.0.1:8000/api/turn";
final String LESSON_ID = "objects-meaning";
final String PHASE_ID = "concept";

String input = "";
String status = "발문을 입력하고 Enter를 누르세요.";
boolean sending = false;

ArrayList<StudentView> students = new ArrayList<StudentView>();
ArrayList<String> transcript = new ArrayList<String>();

void setup() {
  size(1100, 720);
  textFont(createFont("SansSerif", 16));
  students.add(new StudentView("harin", "하린", "국어사전 뜻", "confused", 0.55));
  students.add(new StudentView("junseo", "준서", "비싼 것", "thinking", 0.35));
  students.add(new StudentView("minji", "민지", "같은 순서 친구", "confused", 0.20));
}

void draw() {
  background(247, 248, 250);

  // Header
  fill(30, 35, 45);
  textSize(26);
  text("SimClass · 즐생 수업 리허설", 36, 52);
  textSize(14);
  fill(100, 108, 120);
  text("Lesson: 물건의 의미는 무엇일까요?  ·  Phase: 개념 형성", 36, 78);

  // Student cards
  for (int i = 0; i < students.size(); i++) {
    StudentView s = students.get(i);
    float x = 36 + i * 350;
    float y = 104;
    float w = 320;
    float h = 150;

    fill(255);
    stroke(225, 228, 234);
    strokeWeight(1);
    rect(x, y, w, h, 14);

    noStroke();
    fill(30, 35, 45);
    textSize(20);
    text(s.name, x + 20, y + 34);

    fill(stateColor(s.state));
    textSize(13);
    text(s.state, x + 20, y + 58);

    fill(90, 98, 110);
    textSize(13);
    text("오개념: " + s.misconception, x + 20, y + 84);
    text("mastery: " + nf((float)s.mastery, 1, 2), x + 20, y + 106);

    // mastery bar
    fill(232, 235, 240);
    rect(x + 20, y + 118, w - 40, 8, 4);
    fill(80, 130, 220);
    rect(x + 20, y + 118, (w - 40) * (float)s.mastery, 8, 4);
  }

  // Transcript
  fill(255);
  stroke(225, 228, 234);
  rect(36, 280, 1028, 330, 14);
  noStroke();
  fill(30, 35, 45);
  textSize(18);
  text("수업 대화", 56, 312);
  textSize(14);
  fill(70, 78, 90);
  float ty = 342;
  int start = max(0, transcript.size() - 12);
  for (int i = start; i < transcript.size(); i++) {
    text(transcript.get(i), 56, ty, 980, 40);
    ty += 22;
  }

  // Input
  fill(255);
  stroke(200, 205, 215);
  rect(36, 632, 860, 48, 10);
  noStroke();
  fill(30, 35, 45);
  textSize(16);
  text(input + (frameCount / 30 % 2 == 0 ? "|" : ""), 52, 662);

  // Button
  fill(sending ? color(160, 170, 185) : color(50, 90, 180));
  rect(910, 632, 154, 48, 10);
  fill(255);
  textSize(16);
  text(sending ? "전송 중..." : "발문 전송", 942, 662);

  // Status
  fill(120, 128, 140);
  textSize(12);
  text(status, 36, 704);
}

void keyTyped() {
  if (key == ENTER || key == RETURN) {
    sendTurn();
  } else if (key == BACKSPACE) {
    if (input.length() > 0) input = input.substring(0, input.length() - 1);
  } else if (key != CODED && key != TAB) {
    input += key;
  }
}

void mousePressed() {
  if (mouseX > 910 && mouseX < 1064 && mouseY > 632 && mouseY < 680) {
    sendTurn();
  }
}

void sendTurn() {
  String utterance = input.trim();
  if (utterance.length() == 0 || sending) return;
  input = "";
  sending = true;
  status = "서버에 발문을 보내는 중...";
  transcript.add("T: " + utterance);

  thread(() -> {
    try {
      JSONObject payload = new JSONObject();
      payload.setString("session_id", "demo-1");
      payload.setString("lesson_id", LESSON_ID);
      payload.setString("phase_id", PHASE_ID);
      payload.setString("teacher_utterance", utterance);

      HttpURLConnection conn = (HttpURLConnection) new URL(SERVER_URL).openConnection();
      conn.setRequestMethod("POST");
      conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
      conn.setDoOutput(true);
      byte[] body = payload.toString().getBytes(StandardCharsets.UTF_8);
      try (OutputStream os = conn.getOutputStream()) {
        os.write(body);
      }

      int code = conn.getResponseCode();
      if (code != 200) {
        status = "서버 오류: HTTP " + code;
        sending = false;
        return;
      }

      StringBuilder sb = new StringBuilder();
      try (BufferedReader br = new BufferedReader(
          new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
        String line;
        while ((line = br.readLine()) != null) sb.append(line);
      }

      JSONObject res = parseJSONObject(sb.toString());
      JSONArray arr = res.getJSONArray("students");
      for (int i = 0; i < arr.size(); i++) {
        JSONObject s = arr.getJSONObject(i);
        String name = s.getString("name");
        String text = s.getString("text");
        String state = s.getString("state");
        transcript.add(name + ": " + text);
        for (StudentView sv : students) {
          if (sv.id.equals(s.getString("id"))) {
            sv.state = state;
          }
        }
      }
      status = "응답 도착 · mock 모드";
    } catch (Exception e) {
      status = "연결 실패: " + e.getMessage();
    } finally {
      sending = false;
    }
  });
}

color stateColor(String state) {
  if (state.equals("confused")) return color(200, 90, 80);
  if (state.equals("thinking")) return color(190, 140, 40);
  return color(60, 140, 100);
}

class StudentView {
  String id;
  String name;
  String misconception;
  String state;
  float mastery;

  StudentView(String id, String name, String misconception, String state, float mastery) {
    this.id = id;
    this.name = name;
    this.misconception = misconception;
    this.state = state;
    this.mastery = mastery;
  }
}
