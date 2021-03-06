from easygopigo3 import EasyGoPiGo3

#Set up simple terminology
gpg = EasyGoPiGo3()

def circumNav(gpg, dist_sensor=None, params=None):

    #Initialize distance sensor
    if dist_sensor is None:
        dist_sensor=gpg.init_distance_sensor()

    #Set required variables
    if params is None:
        rad= 200
        h_spd= 400
        m_spd= 200
        l_spd= 30
    else:
        rad = params['rad']
        h_spd = params['h_spd']
        m_spd = params['m_spd']
        l_spd = params['l_spd']

    gpg.set_speed(h_spd)
    ob_dist = dist_sensor.read_mm()
    print("Starting Distance Sensor Reading: {} mm ".format(ob_dist))

    # Drive full bore at the cone
    while ob_dist>= rad:
        gpg.forward()
        ob_dist=dist_sensor.read_mm()
        print("Distance Sensor Reading: {} mm ".format(ob_dist))
    gpg.stop()

    # Back away to the exact distance at a slower speed
    gpg.set_speed(l_spd)
    while ob_dist< rad:
        gpg.backward()
        ob_dist=dist_sensor.read_mm()
        print("Distance Sensor Reading: {} mm ".format(ob_dist))  
    gpg.stop()
    print("MADE IT!")

    # Set the speed to medium speed
    gpg.set_speed(m_spd)
    print("I will now cicle the cone at {} mm ".format(ob_dist))

    # Circumscibe a circle around the cone
    # rotate gpg 90 degrees to prep for the orbit
    gpg.turn_degrees(-90)

    # Complete the orbit
    gpg.orbit(180,(2*ob_dist/10))

    # Rotate back to facing the cone
    gpg.turn_degrees(90)
    ob_dist=dist_sensor.read_mm()
    print("The cone is now at: {} mm ".format(ob_dist))

    # Return to a base position
    print("That was fun... I go home now") 
    gpg.drive_cm(-20,True)
