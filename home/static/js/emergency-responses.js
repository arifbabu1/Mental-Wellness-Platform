// Fallback responses used only when the local Django/Ollama chatbot endpoint is unavailable.
const emergencyResponses = {
  greeting: [
    "Hello! I'm here to help you 24/7. What's on your mind?",
    "Hi there. I'm glad you reached out. How can I support you today?",
    "Welcome. I'm here to listen without judgment. What would you like to talk about?"
  ],
  personal_ai: [
    "I'm here and ready to support you. More importantly, how are you feeling right now?",
    "I'm focused on helping you. What would feel most useful in this moment?",
    "Thank you for asking. I'm here with you. What's on your mind?"
  ],
  anxiety: [
    "Anxiety can feel intense, but it can pass. Try breathing in for 4 counts and out for 6 counts three times.",
    "Let's ground for a moment: name 5 things you can see, 4 you can touch, 3 you can hear, 2 you can smell, and 1 you can taste.",
    "Your body is sounding an alarm. If you are not in immediate danger, place your feet on the floor and take one slow breath."
  ],
  depression: [
    "I'm sorry this feels so heavy. You do not have to carry it alone. What has been the hardest part today?",
    "Depression can make things feel hopeless, but feelings are not facts. One small step, like drinking water or messaging someone, can matter.",
    "You deserve support. If this has been lasting or worsening, talking with a therapist or doctor can help."
  ],
  stress: [
    "That sounds like a lot to hold. Try choosing one small next step and pausing anything that is not urgent.",
    "Stress can put your whole system on high alert. Take a slow breath, relax your shoulders, and name what is most within your control.",
    "You are not failing; you are overloaded. What is one thing you can set down for the next ten minutes?"
  ],
  loneliness: [
    "Loneliness hurts. Reaching out here was a real step toward connection. Is there one trusted person you could message today?",
    "You deserve connection and care. I can stay with you while you put words to what feels most lonely.",
    "Feeling alone does not mean you are unworthy. What kind of support would feel safe right now?"
  ],
  sleep: [
    "Sleep trouble can make everything harder. Try dimming lights, putting screens away, and doing slow breathing for a few minutes.",
    "If your mind is racing, write down the worry and tell yourself you can return to it tomorrow.",
    "Rest matters. If sleep problems continue, a health professional can help you find the cause."
  ],
  relationships: [
    "Relationships can be painful when needs or boundaries are unclear. What happened that is weighing on you?",
    "It may help to describe the feeling first: hurt, anger, fear, guilt, or disappointment. Which one fits best?",
    "You deserve respectful connection. What boundary or conversation feels important now?"
  ],
  work: [
    "Work or study pressure can become overwhelming. Your worth is not the same as your productivity.",
    "Try breaking the next task into a ten-minute step. What is the smallest useful action?",
    "Burnout is serious. Rest and support are part of solving it, not a reward after everything is done."
  ],
  selfesteem: [
    "That inner critic can be harsh. What would you say to a friend who was thinking this about themselves?",
    "Your worth is not defined by one mistake, one feeling, or one difficult day.",
    "Self-compassion is a skill. Try naming one thing you handled today, even if it was small."
  ],
  trauma: [
    "I'm sorry you went through that. You deserve safety and support from someone trauma-informed.",
    "If you feel triggered, look around and name where you are. Remind yourself: this is now, and I am here.",
    "Healing from trauma is possible, and it is okay to seek professional help."
  ],
  substance: [
    "Substance struggles often connect to pain or stress. You deserve support without shame.",
    "Recovery can involve many kinds of help: therapy, support groups, medical care, and harm reduction.",
    "If you are in immediate medical danger, call emergency services now."
  ],
  grief: [
    "Grief can come in waves. There is no perfect timeline for it.",
    "I'm sorry for your loss. What memory or feeling is closest to the surface right now?",
    "Be gentle with yourself today. Grief is not something you have to rush through."
  ],
  physical: [
    "Physical and mental health affect each other. If symptoms are severe or sudden, please contact a medical professional.",
    "A small body reset can help: water, food, a short walk, or a few slow breaths.",
    "If pain or illness is affecting your mood, a doctor can help you look at both sides together."
  ],
  financial: [
    "Financial stress can feel frightening. Start with one concrete fact you know and one next action you can take.",
    "Money stress is common and not a measure of your worth.",
    "If this feels unmanageable, support from a trusted person or financial counselor may help."
  ],
  existential: [
    "Questions about meaning can feel heavy. You do not need every answer tonight.",
    "Meaning is often built from small moments of connection, care, or purpose.",
    "What has mattered to you, even a little, in the past?"
  ],
  help: [
    "I'm here to help. Do you need emotional support, coping strategies, platform guidance, or immediate emergency help?",
    "You've taken a good step by reaching out. What feels most urgent right now?",
    "I can listen, suggest grounding steps, or point you toward support. What would help most?"
  ],
  breathing: [
    "Try this with me: breathe in for 3, hold for 3, breathe out for 3. Repeat gently.",
    "Let your shoulders drop. Breathe in through your nose and exhale slowly through your mouth.",
    "Grounding can help: press your feet into the floor and notice the room around you."
  ],
  location: [
    "For immediate support, call the emergency hotline at 16101. You can also use the platform to find doctors and therapists.",
    "The platform can help you browse doctors, book appointments, and find professional support.",
    "If you are in danger or this is a medical emergency, contact emergency services or go to the nearest emergency room."
  ],
  general: [
    "I'm here with you. Can you tell me a little more about what's happening?",
    "Thank you for sharing that. What feels most difficult right now?",
    "You do not have to figure this out alone. What would feel supportive in this moment?"
  ],
  defaultResponses: [
    "I'm here with you. What's bothering you most right now?",
    "I'm listening. What would you like me to understand?",
    "Thank you for telling me. Let's take this one step at a time."
  ]
};
