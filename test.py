<script>
    const API_BASE = 'http://localhost:5000';  // Cambia si despliegas en otro dominio
    let currentSession = {
        session_id: null,
        region_id: null,
        comuna_id: null,
        servicio_id: null,
        action: null,
        servicios: []
    };

    document.getElementById('chatbot-icon').addEventListener('click', () => {
        const window = document.getElementById('chatbot-window');
        window.style.display = window.style.display === 'none' ? 'flex' : 'none';

        if (window.style.display === 'flex' && document.getElementById('chatbot-messages').children.length === 0) {
            addMessage('bot', '👋 ¡Hola! Soy NEOServicios. ¿Me indicas tu comuna?');
        }
    });

    document.getElementById('chatbot-close').addEventListener('click', () => {
        document.getElementById('chatbot-window').style.display = 'none';
    });

    document.getElementById('chatbot-send').addEventListener('click', sendMessage);
    document.getElementById('chatbot-input').addEventListener('keypress', function (e) {
        if (e.key === 'Enter') sendMessage();
    });

    function sendMessage() {
        const input = document.getElementById('chatbot-input');
        const message = input.value.trim();
        if (message === '') return;

        addMessage('user', message);
        input.value = '';

        const requestData = {
            response: message,
            session_id: currentSession.session_id,
            servicio_id: currentSession.servicio_id
        };

        fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            console.log("Respuesta del servidor:", data);

            if (data.session_id) currentSession.session_id = data.session_id;
            if (data.region_id) currentSession.region_id = data.region_id;
            if (data.comuna_id) currentSession.comuna_id = data.comuna_id;
            if (data.servicio_id) currentSession.servicio_id = data.servicio_id;
            if (data.servicios) currentSession.servicios = data.servicios;
            if (data.action) currentSession.action = data.action;

            if (data.response) {
                addMessage('bot', data.response);
            }
        })
        .catch(error => {
            console.error('Error en fetch:', error);
            addMessage('bot', '❌ Ocurrió un error al procesar tu mensaje.');
        });
    }

    function addMessage(sender, text) {
        const chat = document.getElementById('chatbot-messages');
        const msg = document.createElement('div');
        msg.classList.add('message', sender);
        msg.innerHTML = text.replace(/\n/g, "<br>");  // Maneja saltos de línea
        chat.appendChild(msg);
        chat.scrollTop = chat.scrollHeight;
    }
</script>