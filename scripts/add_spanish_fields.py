"""
Add spanish_prompt, spanish_cue, and card_type fields to mx_survival_source.json.

card_type values:
  production_from_audio - Spanish prompt audio plays; learner produces response
  production_from_scene - no natural Spanish prompt; cue alone sets the scene
  recognition           - vocabulary gloss; know what it means when you hear it
  interjection          - pure reaction phrase; cue sets the moment, learner reacts
"""

import json

# Each tuple: (spanish_prompt, spanish_cue, card_type)
# For recognition: spanish_prompt = the Spanish word/phrase itself, spanish_cue = ""

ADDITIONS = [
    # --- mexicanismos (52) ---
    # 0 Ahorita.
    ("¿Para cuándo me lo tienes?", "Le dices que lo harás 'en un rato'.", "production_from_audio"),
    # 1 Ahoritita / ahorita mismo.
    ("Oye, ¿cuándo dices que llegas?", "Enfatizas que llegas en este instante.", "production_from_audio"),
    # 2 ¿Mande?
    ("¡Oye, Ian!", "Te llaman por tu nombre; respondes con cortesía mexicana.", "production_from_audio"),
    # 3 ¿Mande usted?
    ("Disculpe, joven.", "Un desconocido mayor te llama la atención; respondes con formalidad.", "production_from_audio"),
    # 4 ¡Órale!
    ("¿Vamos al concierto esta noche?", "Aceptas con entusiasmo la propuesta de tu amigo.", "production_from_audio"),
    # 5 Sale.
    ("¿Nos vemos a las ocho?", "Confirmas el plan de manera casual.", "production_from_audio"),
    # 6 Va.
    ("¿Me das un jalón al centro?", "Confirmas de forma muy corta que sí.", "production_from_audio"),
    # 7 ¡Ándale!
    ("Ya casi llego, espérame.", "Tu amigo sigue tardando. Lo urges a que se apure.", "production_from_audio"),
    # 8 Ándale pues.
    ("Bueno, yo me voy.", "Tu amigo se despide. Cierras la conversación amigablemente.", "production_from_audio"),
    # 9 ¡Qué chido!
    ("Me compré una moto nueva.", "Tu amigo te da una buena noticia. Reaccionas con entusiasmo — a la mexicana.", "interjection"),
    # 10 ¡Qué padre!
    ("Nos salimos temprano del trabajo hoy.", "Tu compañero te da una buena nueva. Reaccionas con gusto.", "interjection"),
    # 11 ¿Qué onda, güey?
    ("Qué pasó, manito.", "Tu cuate te saluda. Le respondes en el mismo registro.", "production_from_audio"),
    # 12 ¿Qué onda?
    ("¡Qué onda!", "Un amigo te saluda. Le preguntas cómo está — saludo casual.", "production_from_audio"),
    # 13 ¡No manches!
    ("Me robaron el celular en el metro.", "Tu amigo te cuenta que le robaron. Reaccionas con incredulidad — sin groserías.", "interjection"),
    # 14 ¡No mames!
    ("Güey, reprobé el examen.", "Tu amigo de confianza te da una mala noticia. Reaccionas con incredulidad — registro vulgar entre cuates.", "interjection"),
    # 15 ¿Neta?
    ("Me ofrecieron trabajo en Japón.", "Alguien te dice algo increíble. Preguntas si es en serio — a la mexicana.", "production_from_audio"),
    # 16 La neta...
    ("¿Y tú qué opinas?", "Te piden tu opinión honesta. Introduces lo que realmente piensas.", "production_from_audio"),
    # 17 Un cafecito, por favor.
    ("¿Qué le pongo?", "Pides un café usando el diminutivo afectivo mexicano.", "production_from_audio"),
    # 18 Tantito, por favor.
    ("¿Cuánta salsa le echo?", "Pides solo un poco de algo.", "production_from_audio"),
    # 19 Espérame tantito.
    ("Ya vámonos.", "Alguien te apura pero necesitas un momento. Le pides que espere.", "production_from_audio"),
    # 20 ¡Híjole!
    (None, "Acabas de saber que el vuelo se canceló. Reaccionas con sorpresa leve — de forma segura en cualquier contexto.", "interjection"),
    # 21 ¡Chale!
    ("Se canceló el partido.", "Tu amigo te da una mala noticia. Reaccionas con decepción.", "interjection"),
    # 22 N'ombre.
    ("¿Crees que vayan a bajar los precios?", "Alguien propone algo poco probable. Expresas escepticismo fuerte.", "production_from_audio"),
    # 23 Me late.
    ("¿Qué te parece si comemos en ese lugar nuevo?", "Tu amigo propone un plan. Dices que te gusta la idea — a la mexicana.", "production_from_audio"),
    # 24 ¿Qué pedo?
    ("¿Qué pasó, carnal?", "Tu cuate de confianza te saluda en registro informal vulgar. Respondes igual.", "production_from_audio"),
    # 25 Está bien pedo.
    ("¿Cómo está tu primo?", "Un amigo pregunta por alguien que está muy borracho. Describes el estado.", "production_from_audio"),
    # 26 No hay pedo.
    ("Oye, se me olvidó devolverte el dinero.", "Un amigo se disculpa. Lo tranquilizas — entre cuates, registro vulgar OK.", "production_from_audio"),
    # 27 No hay bronca.
    ("Perdón, se me hizo tarde.", "Alguien llega tarde y se disculpa. Le dices que no hay problema — versión más suave.", "production_from_audio"),
    # 28 Pinche...
    ("¿Por qué llegas tarde?", "Explicas algo con el intensificador mexicano — entre amigos.", "production_from_scene"),
    # 29 Hace un pinche frío.
    ("¿Cómo está el clima allá afuera?", "Te preguntan cómo está el tiempo. Describes el frío con el intensificador mexicano.", "production_from_audio"),
    # 30 Está a toda madre.
    ("¿Cómo estuvo el concierto?", "Te preguntan cómo estuvo algo. Dices que estuvo increíble — a toda madre.", "production_from_audio"),
    # 31 Me fue de la chingada.
    ("¿Cómo te fue en la entrevista?", "Un amigo de confianza te pregunta. Le cuentas que todo salió muy mal — vulgar OK.", "production_from_audio"),
    # 32 Vete a la chingada.
    ("Sigues hostigando a alguien que ya te dijo que no.", "Alguien insiste en molestarte después de varios rechazos. Mandas a alguien lejos — grosería fuerte, solo para reconocer.", "production_from_scene"),
    # 33 Me vale madre.
    ("¿Y si te critican en redes?", "Te preguntan si te preocupa algo. Dices que eso te importa absolutamente nada — entre amigos.", "production_from_audio"),
    # 34 Me da igual.
    ("¿Quieres pizza o sushi?", "Te dan a elegir entre opciones. Dices que cualquiera te viene bien — registro seguro.", "production_from_audio"),
    # 35 Está pan comido.
    ("¿Crees que pases el examen?", "Te preguntan si algo es difícil. Dices que es facilísimo — con el modismo mexicano.", "production_from_audio"),
    # 36 ¿Qué te pasó?
    ("Tu amigo llega visiblemente alterado.", "Ves a alguien que claramente está mal. Le preguntas qué le ocurrió.", "production_from_scene"),
    # 37 ¿Qué onda contigo?
    ("Tu cuate lleva un rato actuando raro.", "Tu amigo se está portando extraño. Le preguntas qué le pasa — tono juguetón.", "production_from_scene"),
    # 38 ¿Y ora?
    ("El plan cambió de último momento sin avisarte.", "El plan cambió de golpe y no sabes qué hacer. Preguntas confundido.", "interjection"),
    # 39 Ando bien bruja.
    ("¿Salimos este fin?", "Un amigo te propone salir. Explicas que no puedes porque andas sin dinero.", "production_from_audio"),
    # 40 Lana.
    ("¿Tienes para el taxi?", "Alguien pregunta si traes dinero. Usas la palabra mexicana.", "production_from_audio"),
    # 41 ¿Traes unos varos?
    ("Oye, se me olvidó la cartera.", "Tu amigo dice que no trae cartera. Le preguntas si trae algo de efectivo.", "production_from_audio"),
    # 42 Estuvo bien chido.
    ("¿Cómo estuvo la fiesta?", "Te preguntan cómo estuvo algo. Dices que estuvo muy bueno — con intensificador mexicano.", "production_from_audio"),
    # 43 Me da hueva.
    ("¿Vas al gym hoy?", "Te preguntan si vas a hacer algo. Dices que tienes hueva de hacerlo.", "production_from_audio"),
    # 44 Es bien huevón.
    ("¿Por qué no entregó el proyecto tu compañero?", "Alguien pregunta por qué algo no se hizo. Describes al culpable como muy flojo — entre cuates.", "production_from_audio"),
    # 45 Traigo un hambre...
    ("¿Cuándo comemos?", "Alguien pregunta cuándo van a comer. Dices que traes mucha hambre — a la mexicana.", "production_from_audio"),
    # 46 Bye, cuídate.
    ("Bueno, me tengo que ir.", "Tu amigo se despide. Te despides con el típico cierre de CDMX.", "production_from_audio"),
    # 47 Está carísimo / un dineral.
    ("¿Cuánto te costó el depa?", "Te preguntan el precio de algo. Dices que te pareció carísimo.", "production_from_audio"),
    # 48 Qué rollo.
    ("Para renovar el pasaporte hay que ir tres veces a la oficina.", "Alguien te cuenta un trámite complicado. Expresas que es un fastidio.", "interjection"),
    # 49 Puro choro.
    ("Dice que nunca llegó tarde en su vida.", "Alguien dice algo claramente exagerado. Dices que es puro cuento.", "production_from_audio"),
    # 50 Qué mala onda.
    ("Te cancelaron el vuelo sin ningún aviso.", "Algo o alguien resulta un bajón. Expresas mala vibra.", "interjection"),
    # 51 Es buena onda.
    ("¿Cómo es tu nuevo jefe?", "Te preguntan cómo es alguien. Dices que es muy buen tipo.", "production_from_audio"),

    # --- restaurants (41) ---
    # 52 Dos de pastor con todo, por favor.
    ("¿Qué le doy, joven?", "El taquero te pregunta. Ordenas dos tacos de pastor con todo.", "production_from_audio"),
    # 53 Uno de pastor sin cebolla.
    ("¿Qué va a querer?", "El taquero espera tu orden. Pides un taco de pastor sin cebolla.", "production_from_audio"),
    # 54 Sin cilantro, por favor.
    ("¿Le pongo todo?", "El taquero pregunta si le pone todo. Le dices que sin cilantro.", "production_from_audio"),
    # 55 Para llevar, por favor.
    ("¿Se los pongo aquí o para llevar?", "El taquero pregunta. Dices que te los envuelva para llevar.", "production_from_audio"),
    # 56 Para aquí.
    ("¿Se los pongo aquí o para llevar?", "El taquero pregunta. Dices que vas a comer en el lugar.", "production_from_audio"),
    # 57 ¿Qué me recomienda?
    ("¿Qué va a ordenar?", "El mesero espera tu orden. Le preguntas qué recomienda.", "production_from_audio"),
    # 58 ¿Está picante?
    ("¿Le echo salsa?", "El taquero ofrece ponerte salsa. Preguntas si pica antes de que lo haga.", "production_from_audio"),
    # 59 ¿Cuál es la menos picosa?
    ("Tenemos tres salsas.", "El mesero te muestra las salsas. Preguntas cuál pica menos.", "production_from_audio"),
    # 60 La cuenta, por favor.
    ("¿Todo bien con su platillo?", "El mesero pasa por tu mesa. Pides la cuenta.", "production_from_audio"),
    # 61 ¿Aceptan tarjeta?
    ("¿Va a ser algo más?", "El mesero te pregunta si necesitas algo más. Aprovechas para preguntar si aceptan tarjeta.", "production_from_audio"),
    # 62 Solo efectivo.
    ("¿Puedo pagar con tarjeta?", "El cliente pregunta por tarjeta. El puesto informa que solo aceptan efectivo.", "production_from_audio"),
    # 63 Échele salsa, por favor.
    ("¿Le pongo algo?", "El taquero pregunta si le agrega algo. Le pides que le eche salsa.", "production_from_audio"),
    # 64 ¿Me regala unas tortillas más?
    ("¿Necesita algo más?", "El mesero pregunta si necesitas algo. Pides más tortillas con la fórmula mexicana.", "production_from_audio"),
    # 65 ¿Me regala una Coca, por favor?
    ("¿Qué le traigo de tomar?", "El mesero pregunta qué tomas. Pides una Coca con la fórmula mexicana de cortesía.", "production_from_audio"),
    # 66 Suadero
    ("Suadero", "", "recognition"),
    # 67 Lengua
    ("Lengua", "", "recognition"),
    # 68 Tripa
    ("Tripa", "", "recognition"),
    # 69 Campechano
    ("Campechano", "", "recognition"),
    # 70 Gringa
    ("Gringa", "", "recognition"),
    # 71 Carnitas
    ("Carnitas", "", "recognition"),
    # 72 Al pastor
    ("Al pastor", "", "recognition"),
    # 73 Tlacoyo / huarache / sope
    ("Tlacoyo, huarache, sope", "", "recognition"),
    # 74 Con todo.
    ("¿Cómo lo quiere?", "El taquero pregunta cómo lo quieres. Dices que con todo.", "production_from_audio"),
    # 75 Sin frijoles.
    ("¿Con todo?", "El cocinero pregunta si va con todo. Dices que sin frijoles.", "production_from_audio"),
    # 76 ¿Me trae unos limones?
    ("¿Necesita algo?", "El mesero pregunta si necesitas algo. Pides limones.", "production_from_audio"),
    # 77 ¿Qué lleva este platillo?
    ("Ya voy a anotar su orden.", "El mesero está listo para anotar. Antes de ordenar, preguntas qué lleva el platillo.", "production_from_audio"),
    # 78 No como carne.
    ("¿Ya va a ordenar?", "El mesero espera. Le informas que no comes carne.", "production_from_audio"),
    # 79 ¿Tiene carne? Soy vegetariano.
    ("Este mole lleva pollo.", "El mesero describe un platillo. Preguntas si tiene carne y aclaras que eres vegetariano.", "production_from_audio"),
    # 80 ¿Lleva manteca?
    ("Los frijoles están muy buenos.", "El mesero recomienda los frijoles. Preguntas si llevan manteca — revisión vegetariana.", "production_from_audio"),
    # 81 ¿Nos divide la cuenta?
    ("¿Todo en una sola cuenta?", "El mesero pregunta cómo va la cuenta. Pides que la divida entre los del grupo.", "production_from_audio"),
    # 82 ¿La propina está incluida?
    ("Aquí tiene su cuenta.", "El mesero te trae la cuenta. Preguntas si la propina ya está incluida.", "production_from_audio"),
    # 83 Agréguele el quince, por favor.
    ("¿Cuánto de propina le agrego?", "El mesero tiene la terminal. Le dices que agregue el 15% de propina.", "production_from_audio"),
    # 84 Una botella de agua, por favor.
    ("¿Qué le traigo de tomar?", "El mesero pregunta qué tomas. Pides agua embotellada.", "production_from_audio"),
    # 85 Agua natural.
    ("¿Con gas o natural?", "El mesero pregunta el tipo de agua. Pides sin gas.", "production_from_audio"),
    # 86 Agua mineral.
    ("¿Con gas o natural?", "El mesero pregunta el tipo de agua. Pides con gas.", "production_from_audio"),
    # 87 ¿De qué son las aguas?
    ("¿Qué va a tomar?", "El mesero espera tu orden de bebida. Preguntas qué sabores de aguas frescas tienen.", "production_from_audio"),
    # 88 Agua de jamaica
    ("Agua de jamaica", "", "recognition"),
    # 89 El menú del día / la comida corrida.
    ("¿Ya va a ordenar?", "El mesero espera. Pides el menú del día — la opción más económica y típica.", "production_from_audio"),
    # 90 Ya terminé, gracias.
    ("¿Le retiro el plato?", "El mesero pregunta si puede llevarse el plato. Lo confirmas.", "production_from_audio"),
    # 91 Estuvo riquísimo.
    ("¿Cómo estuvo todo?", "El mesero pregunta cómo estuvo la comida. Le dices que estuvo deliciosa.", "production_from_audio"),
    # 92 ¿Me lo pone para llevar?
    ("¿Algo más?", "Te quedan sobras. Le pides al mesero que te las ponga para llevar.", "production_from_audio"),

    # --- transport (30) ---
    # 93 ¿Está libre?
    ("Un taxi pasa despacio frente a ti.", "Ves un taxi que puede estar disponible. Preguntas si está libre.", "production_from_scene"),
    # 94 ¿Cuánto me cobra hasta la Roma?
    ("¿A dónde va?", "El taxista pregunta a dónde vas. Preguntas el precio antes de subir.", "production_from_audio"),
    # 95 ¿Usa taxímetro?
    ("¿A dónde lo llevo?", "El taxista está listo para ir. Preguntas si usa taxímetro.", "production_from_audio"),
    # 96 Aquí me deja, por favor.
    ("¿Dónde lo dejo?", "El chofer pregunta dónde te baja. Le dices que aquí.", "production_from_audio"),
    # 97 En la próxima esquina, por favor.
    ("¿Dónde lo dejo?", "El chofer pregunta dónde pararte. Le dices que en la próxima esquina.", "production_from_audio"),
    # 98 Más adelante, por favor.
    ("¿Aquí lo dejo?", "El chofer ofrece parar. Le pides que avance un poco más.", "production_from_audio"),
    # 99 Aquí está bien.
    ("¿Aquí lo dejo?", "El chofer pregunta si ya es aquí. Confirmas que sí.", "production_from_audio"),
    # 100 ¿Me espera tantito?
    ("Ya llegamos.", "El taxista indica que llegaron. Le pides que espere un momento.", "production_from_audio"),
    # 101 Estoy en la entrada de... / mejor véngame por...
    ("Ya llegué al pin, ¿dónde está?", "Tu Uber no te encuentra en el pin. Le explicas por dónde estás exactamente.", "production_from_audio"),
    # 102 El metro.
    ("El metro", "", "recognition"),
    # 103 El Metrobús.
    ("El Metrobús", "", "recognition"),
    # 104 Pesero / combi / micro.
    ("Pesero, combi, micro", "", "recognition"),
    # 105 ¡Bajan!
    ("Llevas rato en el pesero y ya llegaste a tu parada.", "Estás en el pesero y quieres bajarte. Avisas al chofer.", "production_from_scene"),
    # 106 ¿Cuánto es el pasaje?
    ("¿Va a subir?", "El pesero para. Preguntas cuánto cuesta el pasaje.", "production_from_audio"),
    # 107 La tarjeta del metro / MI Movilidad.
    ("La tarjeta del metro / MI Movilidad", "", "recognition"),
    # 108 ¿Esta parada es para...?
    ("Siguiente parada: Insurgentes.", "Oyes el anuncio de la siguiente parada. Confirmas si es la que necesitas.", "production_from_audio"),
    # 109 ¿Qué línea va a Coyoacán?
    ("¿En qué le puedo ayudar?", "El empleado de información del metro te atiende. Preguntas qué línea va a tu destino.", "production_from_audio"),
    # 110 ¿Dónde hago transbordo?
    ("¿A dónde va?", "Alguien te pregunta a dónde vas para ayudarte. Preguntas dónde hacer transbordo.", "production_from_audio"),
    # 111 Disculpe, ¿cómo llego a...?
    ("Ves a alguien en la calle que parece conocer la zona.", "Quieres pedir indicaciones a un desconocido. Usas la apertura correcta.", "production_from_scene"),
    # 112 ¿Está lejos? ¿Se puede caminar?
    ("La tienda queda por ahí.", "Alguien te señala vagamente la dirección. Preguntas si puedes ir caminando.", "production_from_audio"),
    # 113 ¿A cuántas cuadras?
    ("Está cerquita.", "Alguien dice que está 'cerquita'. Preguntas cuántas cuadras son exactamente.", "production_from_audio"),
    # 114 Me perdí, ¿me orienta?
    ("¿Anda buscando algo?", "Alguien nota que estás perdido y se acerca. Le dices que te perdiste y pides ayuda.", "production_from_audio"),
    # 115 ¿Sabe llegar?
    ("¿A dónde lo llevo?", "El taxista pregunta a dónde vas. Antes de darle la dirección, verificas que sepa llegar.", "production_from_audio"),
    # 116 ¿Dónde están los taxis autorizados?
    ("Bienvenido al Aeropuerto Internacional.", "Acabas de salir del aeropuerto. Preguntas dónde están los taxis oficiales — crucial para seguridad.", "production_from_scene"),
    # 117 ¿Es usted para Ian?
    ("Un carro se detiene justo frente a ti.", "Un carro para donde estás esperando tu Uber. Confirmas que es el tuyo antes de subir.", "production_from_scene"),
    # 118 ¿Podemos ir por Reforma?
    ("¿Por dónde quiere que vayamos?", "El chofer pregunta la ruta. Le sugieres que vaya por una avenida específica.", "production_from_audio"),
    # 119 Está pesado el tráfico, ¿no?
    ("Llevan diez minutos sin moverse en el mismo tramo.", "El tráfico está horrible. Haces conversación con el chofer.", "production_from_scene"),
    # 120 ¿Tiene cambio de doscientos?
    ("Ya llegamos a tu destino.", "El taxista indica que llegaron. Solo traes un billete grande; preguntas si tiene cambio.", "production_from_scene"),
    # 121 No, gracias. Estoy bien.
    ("¡Taxi! ¡Taxi! ¿Lo llevo, joven?", "Un voceador insiste en llevarte. Lo descartas con cortesía firme.", "production_from_audio"),
    # 122 ¿Cómo llego a la central de autobuses?
    ("¿En qué le puedo ayudar?", "Alguien te atiende y pregunta en qué ayuda. Quieres ir a la terminal de autobuses.", "production_from_audio"),

    # --- shopping (25) ---
    # 123 ¿Cuánto cuesta?
    ("¿En qué le puedo ayudar?", "El vendedor pregunta en qué ayuda. Preguntas el precio de algo.", "production_from_audio"),
    # 124 ¿A cómo el kilo?
    ("¿Cuánto le doy de jitomate?", "El marchante pregunta cuánto quieres. Preguntas el precio por kilo primero.", "production_from_audio"),
    # 125 ¿Me hace un descuento?
    ("¿Qué va a llevar?", "El vendedor del tianguis espera. Pides un descuento.", "production_from_audio"),
    # 126 Está muy caro.
    ("Son trescientos pesos.", "El vendedor dice el precio. Dices que está muy caro — abres el regateo.", "production_from_audio"),
    # 127 ¿Qué es lo último?
    ("¿Cuánto me da?", "El vendedor hace su contraoferta. Preguntas cuál es su precio final.", "production_from_audio"),
    # 128 ¿Me lo guarda?
    ("¿Lo lleva?", "El vendedor pregunta si te lo llevas. Pides que te lo guarde mientras sigues viendo.", "production_from_audio"),
    # 129 Me lo llevo.
    ("¿Cómo quedamos?", "El regateo terminó. Decides comprarlo.", "production_from_audio"),
    # 130 Medio kilo, por favor.
    ("¿Cuánto le pongo?", "El marchante pregunta cuánto quieres. Pides medio kilo.", "production_from_audio"),
    # 131 Un cuarto, por favor.
    ("¿Cuánto le doy?", "El marchante espera. Pides un cuarto de kilo.", "production_from_audio"),
    # 132 Una pieza.
    ("¿Cuántas quiere?", "El vendedor pregunta cuántas. Pides una sola pieza.", "production_from_audio"),
    # 133 ¿Tiene...?
    ("¿En qué le puedo ayudar?", "El empleado pregunta en qué ayuda. Preguntas si tienen el producto que buscas.", "production_from_audio"),
    # 134 ¿Me lo puedo probar?
    ("¿Le gustó algo?", "El dependiente pregunta si te gustó algo. Pides probarte la prenda.", "production_from_audio"),
    # 135 ¿Lo tiene en otro color / otra talla?
    ("¿Cómo le quedó?", "El dependiente pregunta cómo te quedó. Preguntas si lo tienen en otra talla o color.", "production_from_audio"),
    # 136 Solo estoy viendo, gracias.
    ("¿Le ayudo en algo?", "Un vendedor se acerca. Le dices amablemente que solo estás viendo.", "production_from_audio"),
    # 137 ¿Lo puedo probar?
    ("¿Quiere llevar algo?", "El marchante pregunta si llevas algo. Antes de comprar, preguntas si puedes probar.", "production_from_audio"),
    # 138 ¿Cuál está para hoy?
    ("Tenemos mangos muy buenos.", "El frutero recomienda mangos. Preguntas cuáles están listos para comer hoy.", "production_from_audio"),
    # 139 ¿Y para mañana / pasado mañana?
    ("Estas están para hoy.", "El frutero acaba de mostrarte las de hoy. Preguntas cuáles estarán listas mañana.", "production_from_audio"),
    # 140 ¿Me lo separa, por favor?
    ("¿Todo junto?", "El marchante pregunta si va todo junto. Pides que lo separe.", "production_from_audio"),
    # 141 Lo pienso y regreso.
    ("¿Se lo envuelvo?", "El vendedor insiste en cerrarte la venta. Dices que lo vas a pensar — salida cortés.", "production_from_audio"),
    # 142 ¿Me da una bolsa?
    ("¿Algo más?", "El cajero pregunta si necesitas algo más. Pides una bolsa.", "production_from_audio"),
    # 143 ¿Dónde pago? / ¿Dónde está la caja?
    ("Ya tienes todo lo que necesitabas.", "Ya escogiste tus artículos. Preguntas dónde se paga.", "production_from_scene"),
    # 144 ¿Me da el ticket?
    ("Son doscientos cincuenta pesos.", "El cajero te dice el total. Pides tu ticket de compra.", "production_from_audio"),
    # 145 ¿Me hace factura?
    ("¿Algo más?", "El cajero pregunta si necesitas algo más. Pides factura para gastos de empresa.", "production_from_audio"),
    # 146 Pago en efectivo.
    ("¿Cómo va a pagar?", "El cajero pregunta cómo pagas. Dices que en efectivo.", "production_from_audio"),
    # 147 Tianguis.
    ("Tianguis", "", "recognition"),

    # --- politeness (25) ---
    # 148 Con permiso.
    ("Hay gente bloqueando el pasillo del metro.", "Necesitas pasar entre personas en un espacio lleno. Usas la fórmula mexicana.", "production_from_scene"),
    # 149 Propio.
    ("Con permiso.", "Alguien te dice 'con permiso' al pasar frente a ti. Respondes con el término mexicano.", "production_from_audio"),
    # 150 Perdón / disculpe.
    ("Chocas accidentalmente con alguien.", "Sin querer le pegas el hombro a alguien. Te disculpas.", "production_from_scene"),
    # 151 Disculpe...
    ("Ves a un desconocido que puede orientarte.", "Quieres preguntarle algo a alguien que no conoces. Captas su atención con cortesía.", "production_from_scene"),
    # 152 Buenos días.
    ("Son las diez de la mañana y entras a la papelería.", "Entras a un comercio por la mañana. Saludas como lo dicta la norma mexicana.", "production_from_scene"),
    # 153 Buenas tardes.
    ("Son las tres de la tarde y entras al banco.", "Entras a un lugar después del mediodía. Saludas.", "production_from_scene"),
    # 154 Buenas noches.
    ("Ya anocheció y llegas al hotel.", "Llegas a un lugar después de que oscureció. Saludas al recepcionista.", "production_from_scene"),
    # 155 Buenas.
    ("Entras a la papelería del barrio a cualquier hora.", "Entras a un comercio y saludas de forma corta y casual.", "production_from_scene"),
    # 156 Buenas tardes.  [entering a small shop]
    ("Son las cuatro de la tarde.", "Entras a una pequeña tienda de la colonia. Saludas al dueño — norma cultural mexicana obligatoria.", "production_from_scene"),
    # 157 Buenas tardes a todos.
    ("Entras a la sala donde ya hay varias personas sentadas.", "Llegas a un lugar donde hay un grupo. Saludas al cuarto completo.", "production_from_scene"),
    # 158 De nada / no hay de qué.
    ("Muchas gracias, me ayudó mucho.", "Alguien te agradece con énfasis. Respondes al agradecimiento.", "production_from_audio"),
    # 159 Para servirle.
    ("Gracias por su ayuda.", "Alguien te agradece formalmente. Respondes con la fórmula mexicana más cálida.", "production_from_audio"),
    # 160 Mucho gusto.
    ("Le presento a mi colega.", "Te presentan a alguien nuevo. Respondes con cortesía.", "production_from_audio"),
    # 161 Igualmente.
    ("Mucho gusto.", "Alguien te dice 'mucho gusto'. Respondes.", "production_from_audio"),
    # 162 ¿Cómo está?
    ("Buenos días.", "Alguien mayor te saluda. Le preguntas cómo está — registro formal con usted.", "production_from_audio"),
    # 163 ¿Cómo estás? / ¿Cómo te va?
    ("¡Qué onda!", "Un amigo te saluda. Le preguntas cómo está — registro informal.", "production_from_audio"),
    # 164 ¿Cómo te va?
    ("Oye, ¿qué pasó?", "Un conocido te saluda. Preguntas cómo le va de manera casual.", "production_from_audio"),
    # 165 Háblame de tú.
    ("Usted sí que sabe de esto.", "Un conocido mayor te habla de usted. Le pides que te hable de tú.", "production_from_audio"),
    # 166 Usted (use the verb form...)
    ("¿Usted gusta de algo?", "Un señor mayor te pregunta algo. Usas usted en tu respuesta — norma con personas mayores en México.", "production_from_audio"),
    # 167 ¿Gusta usted...?
    ("Acaba de llegar un invitado a tu casa.", "Hay un invitado mayor en tu casa. Le ofreces algo de tomar con la forma formal mexicana.", "production_from_scene"),
    # 168 Provecho. / Pásele.
    ("Por favor, siéntese.", "Recibes a alguien en casa o en una reunión. Los invitas a pasar y servirse.", "production_from_audio"),
    # 169 Provecho.
    ("Pasas junto a una mesa donde están comiendo.", "Caminas junto a personas que están comiendo en el restaurante. Dices la cortesía mexicana de paso.", "production_from_scene"),
    # 170 Si Dios quiere.
    ("¿Nos vemos mañana?", "Alguien confirma un plan. Agregas la expresión mexicana de esperanza.", "production_from_audio"),
    # 171 Que te vaya bien.
    ("Bueno, ya me tengo que ir.", "Tu amigo se despide. Lo despides con el cierre mexicano más cálido.", "production_from_audio"),
    # 172 Muchas gracias / mil gracias.
    ("Aquí tiene su pedido.", "Alguien te entrega algo. Agradeces con calidez — usando la versión más mexicana.", "production_from_audio"),

    # --- money_time (25) ---
    # 173 Un billete de quinientos.
    ("Un billete de quinientos", "", "recognition"),
    # 174 ¿Tiene cambio?
    ("Son ochenta pesos.", "El vendedor dice el precio y tú solo traes un billete grande. Preguntas si tienen cambio.", "production_from_audio"),
    # 175 ¿Me cambia este billete de quinientos?
    ("¿En qué le ayudo?", "Te atienden en la caja. Pides que te cambien un billete de quinientos.", "production_from_audio"),
    # 176 No traigo cambio.
    ("¿Tiene cambio de cien?", "Alguien te pide cambio de cien. Dices que no traes.", "production_from_audio"),
    # 177 ¿Puedo pagar con tarjeta?
    ("¿Cómo va a pagar?", "El cajero pregunta cómo pagas. Preguntas si aceptan tarjeta.", "production_from_audio"),
    # 178 Pago sin contacto.
    ("Pago sin contacto", "", "recognition"),
    # 179 El cajero (automático).
    ("El cajero automático", "", "recognition"),
    # 180 Son las tres y cuarto.
    ("¿Qué hora es?", "Alguien te pregunta la hora. Son las tres y cuarto.", "production_from_audio"),
    # 181 Cuarto para las cuatro.
    ("¿Qué hora es?", "Alguien te pregunta la hora. Faltan quince minutos para las cuatro — usa la forma mexicana.", "production_from_audio"),
    # 182 ¿Qué hora es? / ¿Me da la hora?
    ("Ves a alguien con reloj en la calle.", "Necesitas saber la hora y no traes celular. Preguntas cortésmente a un desconocido.", "production_from_scene"),
    # 183 ¿A qué hora abren / cierran?
    ("¿En qué le puedo ayudar?", "Alguien te atiende por teléfono o en persona. Preguntas el horario.", "production_from_audio"),
    # 184 Al rato.
    ("¿Cuándo vienes?", "Alguien pregunta cuándo llegas. Dices que más tarde — de manera vaga.", "production_from_audio"),
    # 185 Luego luego.
    ("¿Para cuándo lo necesitas?", "Alguien pregunta cuándo necesitas algo. Dices que de inmediato — con el doble mexicano.", "production_from_audio"),
    # 186 En un rato.
    ("¿Cuándo está listo?", "Alguien pregunta cuándo estará listo algo. Dices que en un momento — más concreto que 'al rato'.", "production_from_audio"),
    # 187 Antier.
    ("¿Cuándo pasó eso?", "Alguien pregunta cuándo ocurrió algo. Fue hace dos días — usa el término mexicano.", "production_from_audio"),
    # 188 Pasado mañana.
    ("¿Para cuándo lo quiere?", "Alguien pregunta para cuándo necesitas algo. Dices que para dentro de dos días.", "production_from_audio"),
    # 189 ¿Cuánto le debo?
    ("¿Ya es todo?", "El vendedor pregunta si es todo. Preguntas cuánto debes pagar — forma más cortés.", "production_from_audio"),
    # 190 ¿Ése es el precio final?
    ("Le hago el descuento.", "El vendedor te ofrece un descuento. Verificas si ese ya es el precio definitivo.", "production_from_audio"),
    # 191 ¿Ya con IVA?
    ("Son quinientos pesos.", "El vendedor te dice el precio. Preguntas si ya incluye el IVA.", "production_from_audio"),
    # 192 Quédese con el cambio.
    ("Aquí tiene su cambio.", "El taxista te da el cambio. Le dices que se lo quede como propina.", "production_from_audio"),
    # 193 ¿Cuánto tarda?
    ("Su orden ya está tomada.", "El mesero o la taquilla tomó tu orden. Preguntas cuánto tardará.", "production_from_audio"),
    # 194 ¿Cuánto lleva esperando?
    ("Llevas rato en la fila y alguien más llega.", "Alguien más también lleva esperando. Preguntas cuánto lleva esperando.", "production_from_scene"),
    # 195 Cien varos / un billete.
    ("Cien varos, un billete", "", "recognition"),
    # 196 Un veinte.
    ("Un veinte", "", "recognition"),
    # 197 Como a las seis de la tarde.
    ("¿A qué hora terminas?", "Alguien pregunta a qué hora terminas. Dices que como a las seis de la tarde.", "production_from_audio"),

    # --- reactions (25) ---
    # 198 ¡Claro! / ¡Por supuesto!
    ("¿Me puedes ayudar con esto?", "Alguien te pide ayuda. Aceptas con entusiasmo.", "production_from_audio"),
    # 199 ¡Cómo no!
    ("¿Me puede dar información?", "Alguien te pide información. Afirmas con la fórmula mexicana cálida.", "production_from_audio"),
    # 200 Así es.
    ("Entonces el vuelo sale a las cinco.", "Alguien resume algo correctamente. Confirmas que es así.", "production_from_audio"),
    # 201 ¿En serio? / ¡No me digas!
    ("Me acaban de dar trabajo en Nueva York.", "Un amigo te da una noticia sorprendente. Reaccionas con asombro.", "production_from_audio"),
    # 202 ¡Qué barbaridad!
    ("Le robaron la cartera en el metro.", "Alguien te cuenta algo grave. Reaccionas con indignación o consternación.", "interjection"),
    # 203 ¡Qué lata!
    ("Hay que hacer fila dos horas para el trámite.", "Alguien te describe un proceso tedioso. Expresas que es un fastidio.", "interjection"),
    # 204 ¡Qué oso!
    ("Se me cayó el plato enfrente de todos en el restaurante.", "Alguien te describe una situación muy vergonzosa. Reaccionas.", "interjection"),
    # 205 Qué pena / qué oso.
    ("¿No te dio pena hablar enfrente de todos?", "Alguien pregunta si algo te dio vergüenza. Expresas que sí, mucha.", "production_from_audio"),
    # 206 Pobrecito / pobrecita.
    ("Mi perro se enfermó.", "Alguien te cuenta que algo malo le pasó a alguien. Expresas lástima.", "interjection"),
    # 207 Pues...
    ("¿Qué opinas?", "Alguien te pide tu opinión. Usas el muletilla para ganar tiempo.", "production_from_audio"),
    # 208 O sea...
    ("¿Qué quieres decir con eso?", "Alguien pide que aclares algo. Usas el muletilla mexicano para reformular.", "production_from_audio"),
    # 209 Pues no sé, ¿no?
    ("¿Qué te parece si vamos mañana?", "Alguien te propone algo. Hedgeas tu respuesta a la mexicana.", "production_from_audio"),
    # 210 ...¿no?
    ("Hace mucho calor hoy.", "Haces un comentario y buscas que el otro esté de acuerdo. Añades la coletilla mexicana.", "production_from_scene"),
    # 211 ...¿verdad?
    ("Esto está muy rico.", "Alguien prueba algo bueno. Añades la coletilla para invitar al acuerdo.", "production_from_scene"),
    # 212 ¿Y qué?
    ("Me van a criticar.", "Alguien expresa preocupación por lo que dirán. Le preguntas con descaro qué importa eso.", "production_from_audio"),
    # 213 Olvídalo / déjalo así.
    ("Oye, ¿qué pasó al final con lo del carro?", "Alguien pregunta sobre algo que ya no vale la pena discutir. Dices que ya no importa.", "production_from_audio"),
    # 214 Ni idea.
    ("¿Sabes a qué hora cierra?", "Alguien te pregunta algo que no sabes. Dices que no tienes la menor idea.", "production_from_audio"),
    # 215 Quién sabe. / Sepa.
    ("¿Vendrá María a la fiesta?", "Alguien pregunta algo incierto. Dices que quién sabe — usando la forma mexicana 'sepa'.", "production_from_audio"),
    # 216 Depende.
    ("¿Vas a ir?", "Alguien te pregunta si vas. Dices que depende.", "production_from_audio"),
    # 217 Y ya. / Punto.
    ("Pero sigo sin entender por qué.", "Alguien insiste en reabrir un tema cerrado. Pones punto final.", "production_from_audio"),
    # 218 ¡Felicidades!
    ("Hoy es mi cumpleaños.", "Alguien te cuenta una buena noticia o su cumpleaños. Lo felicitas.", "production_from_audio"),
    # 219 ¡Salud!
    ("Levantan las copas en la mesa.", "Todos levantan la copa. Haces el brindis mexicano.", "production_from_scene"),
    # 220 No te preocupes / no hay problema.
    ("Ay, se me olvidó devolverte el dinero.", "Un amigo se disculpa. Lo tranquilizas diciéndole que no hay problema.", "production_from_audio"),
    # 221 No te apures.
    ("Perdón, voy llegando tarde.", "Alguien se disculpa por tardar. Usas la frase mexicana para decirle que no se preocupe.", "production_from_audio"),
    # 222 Está bien / está bueno.
    ("¿Te parece si nos vemos a las tres?", "Alguien propone un horario. Dices que está bien.", "production_from_audio"),

    # --- trouble (25) ---
    # 223 Me siento mal.
    ("¿Cómo andas?", "Alguien te pregunta cómo estás. Dices que no te sientes bien.", "production_from_audio"),
    # 224 Me duele el estómago.
    ("¿Qué tienes?", "Alguien pregunta qué te pasa. Dices que te duele el estómago.", "production_from_audio"),
    # 225 Tengo diarrea.
    ("¿Qué síntomas tiene?", "El farmacéutico pregunta tus síntomas. Le describes el principal.", "production_from_audio"),
    # 226 ¿Tiene algo para la diarrea?
    ("¿En qué le puedo ayudar?", "El farmacéutico te atiende. Preguntas qué tienen para la diarrea.", "production_from_audio"),
    # 227 Suero Vida Oral, por favor.
    ("¿Algo más?", "El farmacéutico pregunta si necesitas algo más. Pides el suero de rehidratación oral por su nombre de marca.", "production_from_audio"),
    # 228 ¿Hay baño? / ¿Dónde está el baño?
    ("¿En qué le ayudo?", "Necesitas el baño urgentemente. Preguntas dónde está.", "production_from_audio"),
    # 229 ¿Qué me recomienda para...?
    ("¿Qué tiene?", "El farmacéutico pregunta qué te pasa. Preguntas qué te recomienda para tu malestar.", "production_from_audio"),
    # 230 Farmacia con consultorio.
    ("Farmacia con consultorio", "", "recognition"),
    # 231 Necesito un doctor.
    ("¿Se siente bien?", "Alguien nota que estás mal y pregunta. Dices que necesitas ver a un médico.", "production_from_audio"),
    # 232 Soy alérgico a... / Soy alérgica a...
    ("¿Alguna alergia conocida?", "El médico o farmacéutico pregunta por alergias. Declaras la tuya.", "production_from_audio"),
    # 233 ¡Ayuda! / ¡Socorro!
    (None, "Estás en peligro real o ves a alguien en peligro. Gritas pidiendo auxilio.", "interjection"),
    # 234 Me robaron.
    ("¿Qué pasó?", "Alguien nota que algo anda mal y pregunta. Reportas que te robaron.", "production_from_audio"),
    # 235 Se me perdió...
    ("¿Qué buscas?", "Alguien nota que estás buscando algo. Le dices que se te perdió — con el reflexivo mexicano.", "production_from_audio"),
    # 236 ¿Es seguro por aquí?
    ("¿En qué le ayudo?", "El recepcionista del hotel pregunta. Quieres saber si la zona es segura a esta hora.", "production_from_audio"),
    # 237 Déjeme en paz, por favor.
    ("Oiga, oiga, ¿quiere un tour? ¿Taxi? ¿Artesanías?", "Un vendedor insiste y ya lo rechazaste varias veces. Le pides firme pero cortésmente que te deje en paz.", "production_from_audio"),
    # 238 Estoy perdido / perdida.
    ("¿Anda buscando algo?", "Alguien nota que estás desorientado y pregunta. Dices que te perdiste y pides orientación.", "production_from_audio"),
    # 239 ¿Me puede ayudar?
    ("¿En qué le puedo ayudar?", "Alguien ofrece ayuda. Aceptas y pides lo que necesitas.", "production_from_audio"),
    # 240 No hablo bien español, disculpe.
    ("Habla muy rápido contigo en español.", "Alguien te habla rápido. Te disculpas y aclaras que tu español no es perfecto.", "production_from_audio"),
    # 241 ¿Puede hablar más despacio, por favor?
    ("Sigue hablando a velocidad normal.", "Alguien habla muy rápido y no entiendes. Pides que hable más despacio.", "production_from_audio"),
    # 242 ¿Me lo repite, por favor?
    ("Dice algo que no alcanzas a entender.", "Alguien dice algo pero no lo escuchaste bien. Pides que lo repita.", "production_from_audio"),
    # 243 No le entendí.
    ("Termina de explicarte algo.", "Alguien termina de hablar pero no entendiste nada. Lo dices — forma mexicana con 'le'.", "production_from_audio"),
    # 244 ¿Qué quiere decir...?
    ("Te usan una palabra que no reconoces.", "Alguien usa una palabra que no conoces. Preguntas qué significa.", "production_from_audio"),
    # 245 Dejé mi... en el hotel.
    ("¿Trae su pasaporte?", "Alguien pide un documento que dejaste en el hotel. Explicas que lo dejaste ahí.", "production_from_audio"),
    # 246 ¿El agua es potable / se puede tomar?
    ("¿Quiere agua?", "Alguien te ofrece agua. Preguntas si es potable antes de tomar.", "production_from_audio"),
    # 247 ¿Esto se puede comer sin problema?
    ("Señalas algo en el puesto de comida.", "Ves algo en el puesto que no reconoces. Preguntas si es seguro comer.", "production_from_scene"),
]


def main():
    with open("/home/claude/dev/deck-augment/out/mx_survival_source.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) == len(ADDITIONS), f"Mismatch: {len(data)} entries vs {len(ADDITIONS)} additions"

    for entry, (prompt, cue, card_type) in zip(data, ADDITIONS):
        entry["spanish_prompt"] = prompt
        entry["spanish_cue"] = cue
        entry["card_type"] = card_type

    # Validate JSON round-trip
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    parsed = json.loads(serialized)
    assert len(parsed) == len(data), "Round-trip parse failed"

    with open("/home/claude/dev/deck-augment/out/mx_survival_source.json", "w", encoding="utf-8") as f:
        f.write(serialized + "\n")

    # Stats
    non_null = sum(1 for e in data if e["spanish_prompt"] is not None)
    null_count = sum(1 for e in data if e["spanish_prompt"] is None)
    from collections import Counter
    type_counts = Counter(e["card_type"] for e in data)
    print(f"Total entries: {len(data)}")
    print(f"spanish_prompt non-null: {non_null}")
    print(f"spanish_prompt null: {null_count}")
    print("\ncard_type breakdown:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")

    # Print 5 sample entries from different categories
    samples = [
        next(e for e in data if e["category"] == "mexicanismos" and e["spanish"] == "Sale."),
        next(e for e in data if e["category"] == "restaurants" and "Dos de pastor" in e["spanish"]),
        next(e for e in data if e["category"] == "transport" and "taxímetro" in e["spanish"]),
        next(e for e in data if e["category"] == "politeness" and "Propio" in e["spanish"]),
        next(e for e in data if e["category"] == "trouble" and "diarrea" in e["spanish"] and "Tiene" in e["spanish"]),
    ]
    print("\n--- 5 Sample Entries ---")
    for s in samples:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()
