import limacharlie
import openai
import os
import time

openai.api_key = os.getenv("open_apikey")

def main():

    # Create an instance of the LC SDK.
    man = limacharlie.Manager()
    sensors = man.sensors()
    command_line = []
    ai_responses = []
    the_end_times = int(time.time())

    # Get all NEW_PROCESS event CLI Args and put them into a list
    for sensor in sensors:
        # 3600 seconds is the equivalent of 1 hour
        data = sensor.getHistoricEvents(start=(the_end_times - 3600), end=the_end_times, eventType="NEW_PROCESS")
        for stuff in data:
            command_line.append(stuff.get('event').get('COMMAND_LINE'))
    
    # De-duping CLI args to reduce API quota useage
    de_dupe_commands = list(set(command_line))
    with open('limacharlie_ai_research', 'w') as file:
        for command in de_dupe_commands:
            prompt = "Is this command malicious?:\n{} -^-'".format(command)
            response = openai.Completion.create(
                                                model="text-davinci-003",
                                                prompt=prompt,
                                                temperature=0,
                                                max_tokens=64,
                                                top_p=1.0,
                                                frequency_penalty=0.0,
                                                presence_penalty=0.0,
                                                stop=["-^-'"]
                                                )
            file.write("Command Line Arg: {}\nAI Determination: {}\n\n_____\n".format(command, response.choices[0].text.strip('\n')))
            time.sleep(3.2)

if __name__ == '__main__':
    main()
