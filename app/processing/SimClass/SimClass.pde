import java.net.HttpURLConnection;
import java.net.URL;
import java.io.OutputStream;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.concurrent.LinkedBlockingQueue;
import javax.sound.sampled.AudioFileFormat;
import javax.sound.sampled.AudioFormat;
import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.Clip;
import javax.sound.sampled.DataLine;
import javax.sound.sampled.TargetDataLine;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import processing.data.JSONArray;
import processing.data.JSONObject;

// SimClass — Processing client (MVP + HWP ingest)
// Sends a teacher utterance to FastAPI and renders mock student responses.

String SERVER_BASE = "http://127.0.0.1:8010";
final String LESSON_ID = "objects-meaning";
final String PHASE_ID = "concept";

String input = "";
String status = "발문을 입력하고 Enter를 누르세요.";
String lessonTopic = "물건의 의미는 무엇일까요?";
String lessonSummary = "HWP를 불러오면 수업안 요약이 표시됩니다.";
String lessonId = "objects-meaning";
ArrayList<String> misconceptionOptions = new ArrayList<String>();
LinkedBlockingQueue<String> ttsQueue = new LinkedBlockingQueue<String>();
boolean sending = false;
boolean recording = false;
VoiceRecorder recorder;

ArrayList<StudentView> students = new ArrayList<StudentView>();
ArrayList<String> transcript = new ArrayList<String>();

void setup() {
  size(1100, 720);
  textFont(createFont("SansSerif", 16));
  String[] cfg = loadStrings("server.txt");
  if (cfg != null && cfg.length > 0 && cfg[0].trim().length() > 0) {
    SERVER_BASE = cfg[0].trim();
  }
  students.add(new StudentView("harin", "하린", "국어사전 뜻", "confused", 0.55));
  students.add(new StudentView("junseo", "준서", "비싼 것", "thinking", 0.35));
  students.add(new StudentView("minji", "민지", "같은 순서 친구", "confused", 0.20));

  thread(() -> {
    while (true) {
      try {
        playTTS(ttsQueue.take());
      } catch (InterruptedException ignored) {
      }
    }
  });
}

void draw() {
  background(247, 248, 250);

  // Header
  fill(30, 35, 45);
  textSize(26);
  text("SimClass · 즐생 수업 리허설", 36, 48);
  textSize(15);
  fill(70, 78, 90);
  text(lessonTopic, 36, 74, 820, 24);
  textSize(12);
  fill(120, 128, 140);
  text(lessonSummary + "  ·  Phase: 개념 형성", 36, 96, 820, 20);

  // HWP upload button
  fill(245, 247, 250);
  stroke(200, 205, 215);
  rect(884, 22, 180, 42, 10);
  noStroke();
  fill(50, 90, 180);
  textSize(14);
  text("HWP 수업안 불러오기", 898, 48);

  // Voice push-to-talk button
  fill(recording ? color(210, 40, 40) : color(245, 247, 250));
  stroke(200, 205, 215);
  rect(690, 22, 180, 42, 10);
  noStroke();
  fill(recording ? color(255) : color(40, 45, 55));
  textSize(14);
  text(recording ? "녹음 중... 놓으세요" : "음성 입력 (hold)", 706, 48);

  // Student cards
  for (int i = 0; i < students.size(); i++) {
    StudentView s = students.get(i);
    float x = 36 + i * 350;
    float y = 116;
    float w = 320;
    float h = 142;

    fill(255);
    stroke(225, 228, 234);
    strokeWeight(1);
    rect(x, y, w, h, 14);

    noStroke();
    fill(30, 35, 45);
    textSize(20);
    text(s.name, x + 20, y + 32);

    fill(stateColor(s.state));
    textSize(13);
    text(s.state, x + 20, y + 55);

    fill(90, 98, 110);
    textSize(13);
    text("오개념: " + s.misconception, x + 20, y + 80);
    text("mastery: " + nf((float)s.mastery, 1, 2), x + 20, y + 102);

    fill(232, 235, 240);
    rect(x + 20, y + 114, w - 40, 8, 4);
    fill(80, 130, 220);
    rect(x + 20, y + 114, (w - 40) * (float)s.mastery, 8, 4);
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

  // Send button
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
  if (mouseX > 690 && mouseX < 870 && mouseY > 22 && mouseY < 64) {
    startRecording();
    return;
  }
  if (mouseX > 884 && mouseX < 1064 && mouseY > 22 && mouseY < 64) {
    selectInput("HWP 수업안 선택", "hwpSelected");
    return;
  }
  // Click a student card to cycle its misconception.
  if (mouseY > 116 && mouseY < 258) {
    int idx = floor((mouseX - 36) / 350);
    if (idx >= 0 && idx < students.size() && misconceptionOptions.size() > 0) {
      StudentView s = students.get(idx);
      int current = misconceptionOptions.indexOf(s.misconception);
      s.misconception = misconceptionOptions.get((current + 1) % misconceptionOptions.size());
      savePersonas();
      status = s.name + "의 오개념을 바꿨습니다.";
      return;
    }
  }
  if (mouseX > 910 && mouseX < 1064 && mouseY > 632 && mouseY < 680) {
    sendTurn();
  }
}

void mouseReleased() {
  if (recording && mouseButton == LEFT) {
    stopRecordingAndSend();
  }
}

void hwpSelected(File selection) {
  if (selection == null) return;
  status = "HWP를 읽는 중...";
  thread(() -> {
    try {
      byte[] bytes = loadBytes(selection.getAbsolutePath());
      String encoded = Base64.getEncoder().encodeToString(bytes);
      JSONObject payload = new JSONObject();
      payload.setString("filename", selection.getName());
      payload.setString("data_base64", encoded);
      String response = postJson(SERVER_BASE + "/api/lesson/ingest", payload.toString());
      JSONObject lesson = parseJSONObject(response);
      lessonId = lesson.getString("id");
      lessonTopic = lesson.getString("topic");
      int phases = lesson.getJSONArray("phases").size();
      int minutes = lesson.getInt("duration_min");
      lessonSummary = phases + "단계 · " + minutes + "분 · 학생 3명";

      // Refresh misconception choices and generate personas.
      misconceptionOptions.clear();
      JSONArray ms = lesson.getJSONArray("misconceptions");
      for (int i = 0; i < ms.size(); i++) {
        misconceptionOptions.add(ms.getJSONObject(i).getString("text"));
      }
      JSONObject pReq = new JSONObject();
      pReq.setString("lesson_id", lessonId);
      JSONObject pRes = parseJSONObject(
          postJson(SERVER_BASE + "/api/personas/generate", pReq.toString()));
      JSONArray ps = pRes.getJSONArray("personas");
      students.clear();
      for (int i = 0; i < ps.size(); i++) {
        JSONObject p = ps.getJSONObject(i);
        StudentView sv = new StudentView(
            p.getString("id"),
            p.getString("name"),
            p.getString("misconception"),
            "thinking",
            0.5);
        sv.priorKnowledge = p.getString("prior_knowledge");
        sv.confidence = p.getString("confidence");
        sv.speechStyle = p.getString("speech_style");
        try {
          JSONObject m = p.getJSONObject("initial_mastery");
          for (Object key : m.keys()) {
            sv.mastery = m.getFloat((String) key);
            break;
          }
        } catch (Exception ignored) {}
        students.add(sv);
      }

      status = "수업안 파싱 완료" + (lesson.getBoolean("needs_review") ? " · 검토 필요" : "");
      transcript.add("[수업안] " + lessonTopic);
    } catch (Exception e) {
      status = "HWP 파싱 실패: " + e.getMessage();
    }
  });
}

void savePersonas() {
  if (students.size() == 0) return;
  try {
    JSONObject payload = new JSONObject();
    payload.setString("lesson_id", lessonId);
    JSONArray arr = new JSONArray();
    for (int i = 0; i < students.size(); i++) {
      StudentView s = students.get(i);
      JSONObject p = new JSONObject();
      p.setString("id", s.id);
      p.setString("name", s.name);
      p.setString("prior_knowledge", s.priorKnowledge);
      p.setString("misconception_id", "");
      p.setString("misconception", s.misconception);
      p.setString("confidence", s.confidence);
      p.setString("speech_style", s.speechStyle);
      JSONObject m = new JSONObject();
      m.setFloat("kc1", s.mastery);
      p.setJSONObject("initial_mastery", m);
      arr.append(p);
    }
    payload.setJSONArray("personas", arr);
    requestJson("PUT", SERVER_BASE + "/api/personas/" + lessonId, payload.toString());
  } catch (Exception e) {
    status = "페르소나 저장 실패: " + e.getMessage();
  }
}

void startRecording() {
  if (recording) return;
  try {
    recorder = new VoiceRecorder();
    recorder.start();
    recording = true;
    status = "녹음 중... 버튼을 놓으면 전송합니다.";
  } catch (Exception e) {
    status = "마이크 오류: " + e.getMessage();
  }
}

void stopRecordingAndSend() {
  if (!recording || recorder == null) return;
  recording = false;
  try {
    byte[] wav = recorder.stop();
    String encoded = Base64.getEncoder().encodeToString(wav);
    JSONObject payload = new JSONObject();
    payload.setString("filename", "teacher.wav");
    payload.setString("data_base64", encoded);
    thread(() -> {
      try {
        JSONObject res = parseJSONObject(postJson(SERVER_BASE + "/api/asr", payload.toString()));
        String text = res.getString("text");
        input = text;
        transcript.add("[음성] " + text);
        status = "음성 인식 완료 (" + res.getString("mode") + ")";
        sendTurn();
      } catch (Exception e) {
        status = "ASR 실패: " + e.getMessage();
      }
    });
  } catch (Exception e) {
    status = "녹음 종료 실패: " + e.getMessage();
  }
}

void speak(String text) {
  ttsQueue.offer(text);
}

void playTTS(String text) {
  try {
    JSONObject payload = new JSONObject();
    payload.setString("text", text);
    byte[] audio = requestBytes(SERVER_BASE + "/api/tts", payload.toString());
    if (audio.length == 0) return;
    AudioInputStream ais = AudioSystem.getAudioInputStream(new ByteArrayInputStream(audio));
    Clip clip = AudioSystem.getClip();
    clip.open(ais);
    clip.start();
    Thread.sleep(clip.getMicrosecondLength() / 1000 + 150);
    clip.close();
  } catch (Exception ignored) {
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
      String response = postJson(SERVER_BASE + "/api/turn", payload.toString());
      JSONObject res = parseJSONObject(response);
      JSONArray arr = res.getJSONArray("students");
      for (int i = 0; i < arr.size(); i++) {
        JSONObject s = arr.getJSONObject(i);
        String name = s.getString("name");
        String text = s.getString("text");
        String state = s.getString("state");
        transcript.add(name + ": " + text);
        speak(text);
        for (StudentView sv : students) {
          if (sv.id.equals(s.getString("id"))) {
            sv.state = state;
            try {
              JSONObject m = s.getJSONObject("mastery");
              for (Object key : m.keys()) {
                sv.mastery = m.getFloat((String) key);
                break;
              }
            } catch (Exception ignored) {}
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

String postJson(String url, String body) throws Exception {
  return requestJson("POST", url, body);
}

String requestJson(String method, String url, String body) throws Exception {
  HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
  conn.setRequestMethod(method);
  conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
  conn.setDoOutput(true);
  byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
  try (OutputStream os = conn.getOutputStream()) {
    os.write(bytes);
  }
  int code = conn.getResponseCode();
  if (code != 200) {
    throw new RuntimeException("HTTP " + code);
  }
  StringBuilder sb = new StringBuilder();
  try (BufferedReader br = new BufferedReader(
      new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
    String line;
    while ((line = br.readLine()) != null) sb.append(line);
  }
  return sb.toString();
}

byte[] requestBytes(String url, String body) throws Exception {
  HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
  conn.setRequestMethod("POST");
  conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
  conn.setDoOutput(true);
  try (OutputStream os = conn.getOutputStream()) {
    os.write(body.getBytes(StandardCharsets.UTF_8));
  }
  int code = conn.getResponseCode();
  if (code == 204) return new byte[0];
  if (code != 200) throw new RuntimeException("HTTP " + code);
  ByteArrayOutputStream out = new ByteArrayOutputStream();
  try (InputStream in = conn.getInputStream()) {
    byte[] buf = new byte[8192];
    int n;
    while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
  }
  return out.toByteArray();
}

color stateColor(String state) {
  if (state.equals("confused")) return color(200, 90, 80);
  if (state.equals("thinking")) return color(190, 140, 40);
  return color(60, 140, 100);
}

class VoiceRecorder {
  AudioFormat format;
  TargetDataLine line;
  ByteArrayOutputStream pcm;
  Thread thread;
  volatile boolean running;

  void start() throws Exception {
    format = new AudioFormat(16000, 16, 1, true, false);
    DataLine.Info info = new DataLine.Info(TargetDataLine.class, format);
    line = (TargetDataLine) AudioSystem.getLine(info);
    line.open(format);
    line.start();
    pcm = new ByteArrayOutputStream();
    running = true;
    thread = new Thread(() -> {
      byte[] buf = new byte[4096];
      while (running) {
        int n = line.read(buf, 0, buf.length);
        if (n > 0) pcm.write(buf, 0, n);
      }
    });
    thread.start();
  }

  byte[] stop() throws Exception {
    running = false;
    line.stop();
    line.close();
    thread.join(800);
    byte[] raw = pcm.toByteArray();
    AudioInputStream ais = new AudioInputStream(
        new ByteArrayInputStream(raw), format, raw.length / format.getFrameSize());
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    AudioSystem.write(ais, AudioFileFormat.Type.WAVE, out);
    return out.toByteArray();
  }
}

class StudentView {
  String id;
  String name;
  String misconception;
  String state;
  float mastery;
  String priorKnowledge = "중간";
  String confidence = "중간";
  String speechStyle = "";

  StudentView(String id, String name, String misconception, String state, float mastery) {
    this.id = id;
    this.name = name;
    this.misconception = misconception;
    this.state = state;
    this.mastery = mastery;
  }
}
