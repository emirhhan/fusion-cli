import React, {useState} from "react";
import {createRoot} from "react-dom/client";
import "../src/theme/tokens.css";
import "../src/App.css";
import {Conversation, type Mesaj} from "../src/screens/Conversation";

function Scene() {
  const [messages, setMessages] = useState<Mesaj[]>(Array.from({length: 60}, (_, index) => ({
    id: `message-${index}`, rol: "asistan", metin: `${index}: ${"Geçmiş içerik. ".repeat(30)}`,
  })));
  return <main style={{height: "100vh", display: "flex", flexDirection: "column"}}>
    <button onClick={() => setMessages((current) => [...current, {id: "new", rol: "asistan", metin: "Yeni cevap"}])}>Yanıt ekle</button>
    <Conversation mesajlar={messages} running={false} />
  </main>;
}
createRoot(document.getElementById("root")!).render(<Scene />);
