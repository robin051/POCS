import os
import yaml

import panoptes.utils.logger as logger
import panoptes.utils.serial as serial
import panoptes.utils.error as error

@logger.has_logger
class AbstractMount():

    """ 
    Abstract Base class for controlling a mount 
 
    Methods to be implemented:
        - setup_commands
        - get_command
        - check_coordinates
        - sync_coordinates
        - slew_to_coordinates
        - slew_to_park
        - echo

    """

    def __init__(self,
                 config=dict(),
                 commands=dict(),
                 connect=False,
                 ):
        """ 
        Create a new mount class. Sets the following properies:
        
            - self.non_sidereal_available = False
            - self.PEC_available = False
            - self.is_connected = False
            - self.is_slewing = False
            - self.is_initialized = False

        After setting, calls the following:

            - setup_commands
            - setup_serial
        """
        assert len(config) > 0, self.logger.error('Mount requries a config')
        self.config = config.get('mount')

        assert self.config.get('port') is not None, self.logger.error(
            'No port specified, cannot create mount')

        self.logger.info('Creating mount')
        # Setup commands for mount
        self.commands = self.setup_commands(commands)

        # self.logger.debug("Commands available to mount: \n {}".format(self.commands))

        # We set some initial mount properties. May come from config
        self.non_sidereal_available = self.config.setdefault('non_sidereal_available', False)
        self.PEC_available = self.config.setdefault('PEC_available', False)
        self.port = self.config.get('port')

        # Initial states
        self.is_connected = False
        self.is_initialized = False
        self.is_slewing = False

        # Setup connection
        if connect:
            self.connect()

        self.logger.info('Mount created')


    def setup_commands(self, commands):
        """ 
        Does any setup for the commands needed for this mount. Mostly responsible for 
        setting the pre- and post-commands. We could also do some basic checking here
        to make sure required commands are in fact available.
        """
        self.logger.info('Setting up commands for mount')
        # If commands are not passed in, look for configuration file
        # self.logger.debug('commands: {}'.format(commands))
        
        if len(commands) == 0:
            model = self.config.get('model')
            conf_file = "{}/{}/{}.yaml".format(os.getcwd(), 'panoptes/mount/', model)
            if os.path.isfile(conf_file):
                self.logger.debug("Loading mount commands file: {}".format(conf_file))
                try:
                    with open(conf_file, 'r') as f:
                        commands.update(yaml.load(f.read()))
                except OSError as err:
                    self.logger.warning('Cannot load commands config file: {} \n {}'.format(conf_file, err))

        # Get the pre- and post- commands
        self._pre_cmd = commands.setdefault('cmd_pre', ':')
        self._post_cmd = commands.setdefault('cmd_post', '#')

        # Commands to check
        # NOTE: We might want to slim this down and decide which ones fail
        required_commands = [
            'cmd_post', 'cmd_pre', 'get_alt', 'get_az', 'get_dec', 'get_guide_rate', 'get_lat', 'get_local_date',
            'get_local_time', 'get_long', 'get_ra', 'goto_home', 'goto_park', 'is_home', 'is_parked', 'is_sidereal',
            'is_slewing', 'is_tracking', 'mount_info', 'set_alt', 'set_az', 'set_dec', 'set_guide_rate', 'set_lat',
            'set_local_date', 'set_local_time', 'set_long', 'set_ra', 'set_sidereal_rate', 'set_sidereal_tracking',
            'slew', 'start_tracking', 'stop_slewing', 'stop_tracking', 'unpark', 'version',
        ]

        # Give a warning if command not available
        for cmd in required_commands:
            assert commands.get(cmd) is not None, self.logger.warning(
                'No {} command available for mount'.format(cmd))

        self.logger.info('Mount commands set up')
        return commands

    def connect(self):
        """ 
        Connects to the mount via the serial port (self.port). Opens a serial connection
        and calls initialize_mount
        """
        self.logger.info('Connecting to mount')

        if self.is_connected is False:
            try:
                self._connect_serial()
                self.is_connected = True
            except:
                raise error.BadSerialConnection('Cannot create serial connect for mount at port {}'.format(self.port))

        self.logger.debug('Mount connected: {}'.format(self.is_connected ))

        return self.is_connected

    def _connect_serial(self):
        """ 
        Gets up serial connection
        """
        self.logger.info('Making serial connection for mount at {}'.format(self.port))

        self.serial = serial.SerialData(port=self.port)
        self.serial.connect()

        self.logger.info('Mount connected via serial')


    def serial_query(self, cmd):
        """ 
        Performs a send and then returns response. Will do a translate on cmd first. This should
        be the major serial utility for commands. 
        """
        self.logger.debug('Mount Query: {}'.format(cmd))

        self.serial_send(self.get_command(cmd))
        return self.serial_read()

    def serial_send(self, string_command):
        """ 
            Sends a string command to the mount via the serial port. First 'translates'
            the message into the form specific mount can understand
        """
        self.logger.debug("Mount Send: {}".format(string_command))
        self.serial.write(string_command)

    def serial_read(self):
        """ Sends a string command to the mount via the serial port """
        response = self.serial.read()
        self.logger.debug("Mount Read: {}".format(response))
        return response

    def get_command(self, cmd):
        """ Looks up appropriate command for telescope """
        self.logger.debug('Mount Command Lookup: {}'.format(cmd))

        full_command = ''

        # Get the actual command        
        cmd_info = self.commands.get(cmd)

        if cmd_info is not None:
            full_command = "{}{}{}".format(self._pre_cmd, cmd_info.get('cmd'), self._post_cmd)
            self.logger.debug('Mount Full Command: {}'.format(full_command))
        else:
            raise error.InvalidMountCommand('No command for {}'.format(cmd))

        return full_command

    def check_slewing(self):
        """
        Querys mount to determine if it is slewing.
        For some mounts, this is a built in function. For mount which do not have it we will have to 
        write something based on how the coordinates are changing.
        """
        # First send the command to get slewing status
        self.is_slewing = self.serial_query('slewing')
        return self.is_slewing

    def check_coordinates(self):
        """
        Querys the mount for the current position of the mount.
        This will be useful in comparing the position of the mount to the orientation 
        indicated by the accelerometer or by an astrometric plate solve.
        """
        raise NotImplementedError()

    def sync_coordinates(self):
        """
        Takes as input, the actual coordinates (J2000) of the mount and syncs the mount on them.
        Used after a plate solve.
        Once we have a mount model, we would use sync only initially, 
        then subsequent plate solves would be used as input to the model.
        """
        raise NotImplementedError()

    def slew_to_coordinates(self):
        """
        Inputs:
            HA and Dec
            RA tracking rate (in arcsec per second, use 15.0 in absence of tracking model).
            Dec tracking rate (in arcsec per second, use 0.0 in absence of tracking model).
        """
        raise NotImplementedError()

    def initialize_mount(self):
        raise NotImplementedError()

    def slew_to_park(self):
        """
        No inputs, the park position should be defined in configuration
        """
        raise NotImplementedError()

    def echo(self):
        """ mount-specific echo command """
        raise NotImplementedError()

    def ping(self):
        """ Attempts to ping the mount. Can be implemented in various ways """
        raise NotImplementedError()

