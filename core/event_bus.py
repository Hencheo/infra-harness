import json
import redis
import os
import threading
from typing import Callable, Any, Dict, List
from dotenv import load_dotenv

load_dotenv()

class EventBus:
    """
    Event Bus central do Harness utilizando Redis Pub/Sub.
    Responsável pela comunicação assíncrona entre agentes e o core.
    
    CORREÇÃO CRÍTICA: Suporta múltiplos tópicos em um único listener thread,
    evitando o deadlock que ocorria quando subscribe() bloqueava a thread principal.
    """
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", host),
            port=int(os.getenv("REDIS_PORT", port)),
            db=int(os.getenv("REDIS_DB", db)),
            decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()
        self._callbacks: Dict[str, Callable] = {}
        self._listener_thread: threading.Thread = None
        self._running = False

    def publish(self, topic: str, payload: Any):
        """
        Publica uma mensagem em um tópico específico.
        """
        message = json.dumps(payload)
        self.redis_client.publish(topic, message)
        print(f"[EventBus] Publicado em {topic}: {message[:200]}...")

    def subscribe(self, topic: str, callback: Callable[[Any], None]):
        """
        Se inscreve em um tópico e registra o callback.
        NÃO BLOQUEIA a thread chamadora — usa um listener thread compartilhado.
        """
        self._callbacks[topic] = callback
        self.pubsub.subscribe(**{topic: lambda msg, cb=callback: self._handle_message(msg, cb)})
        print(f"[EventBus] Inscrito no tópico: {topic}")
        
        # Inicia o listener thread apenas uma vez
        if not self._running:
            self._running = True
            self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listener_thread.start()

    def subscribe_blocking(self, topic: str, callback: Callable[[Any], None]):
        """
        Subscribe BLOQUEANTE — para o último subscribe do agente (mantém o processo vivo).
        Registra o tópico e depois bloqueia a thread atual no listener.
        """
        self._callbacks[topic] = callback
        self.pubsub.subscribe(**{topic: lambda msg, cb=callback: self._handle_message(msg, cb)})
        print(f"[EventBus] Inscrito (bloqueante) no tópico: {topic}")
        
        # Se já tem um listener thread rodando, para ele e assume o controle da thread atual
        self._running = False
        if self._listener_thread and self._listener_thread.is_alive():
            # O thread daemon morrerá quando bloquearmos aqui
            pass
        
        # Bloqueia a thread atual (mantém o agente vivo)
        self._listen_loop()

    def _listen_loop(self):
        """
        Loop central de escuta. Processa mensagens de TODOS os tópicos inscritos.
        """
        for message in self.pubsub.listen():
            if not self._running and threading.current_thread().daemon:
                break
            if message['type'] == 'message':
                # O callback já é chamado via a lambda definida no subscribe
                pass

    def _handle_message(self, message: dict, callback: Callable):
        """
        Processa a mensagem bruta do Redis e converte para dicionário Python.
        """
        try:
            data = json.loads(message['data'])
            callback(data)
        except Exception as e:
            print(f"[EventBus] Erro ao processar mensagem: {e}")

# Exemplo de uso e teste rápido
if __name__ == "__main__":
    import time

    bus = EventBus()

    def my_callback(data):
        print(f"[Teste] Recebido no tópico 1: {data}")

    def my_callback2(data):
        print(f"[Teste] Recebido no tópico 2: {data}")

    # Agora ambos os subscribes funcionam sem bloquear!
    bus.subscribe("harness.test1", my_callback)
    bus.subscribe("harness.test2", my_callback2)

    time.sleep(1) # Aguarda os subscribes serem efetivados
    bus.publish("harness.test1", {"msg": "Olá do tópico 1!"})
    bus.publish("harness.test2", {"msg": "Olá do tópico 2!"})
    
    time.sleep(2) # Aguarda o processamento
