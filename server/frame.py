import typing
from enum import Enum, auto
from io import BytesIO
from hpack import Encoder, Decoder

# private programs
from .logger import get_logger_set
logger, log = get_logger_set('frame')


class FrameTypes(Enum):
    DATA = b'\x00'
    HEADERS = b'\x01'
    PRIORITY = b'\x02'
    RST_STREAM = b'\x03'
    SETTINGS = b'\x04'
    PUSH_PROMISE = b'\x05'
    PING = b'\x06'
    GOAWAY = b'\x07'
    WINDOW_UPDATE = b'\x08'
    COTINUATION = b'\x09'


class FrameBase(object):
    """docstring for FrameBase"""
    factory = None

    def __init__(self, length: int, type_, flags: bytes, stream_identifier: int):
        self.length = length
        self.type_ = type_
        self.flags = flags
        self.stream_identifier = stream_identifier

    @classmethod
    def get_factory(cls):
        if not cls.factory:
            cls.factory = {klass.FrameType().value: klass for klass in cls.__subclasses__()}
        return cls.factory

    @classmethod
    def create(cls, length, type_, flags, stream_identifier, data=None):
        factory = cls.get_factory()
        return factory[type_](length, type_, flags, stream_identifier, data)

    @classmethod
    def load(cls, frame):
        length = int.from_bytes(frame[:3], 'big', signed=False)
        type_ = frame[3:4]
        flags = frame[4:5]
        stream_identifier = int.from_bytes(frame[5:9], 'big', signed=False)

        factory = cls.get_factory()
        return factory[type_](length, type_, flags, stream_identifier, frame[9:])

    def save(self):
        res = b''
        res += self.length.to_bytes(3, 'big', signed=False)
        res += self.type_
        res += self.flags
        res += self.stream_identifier.to_bytes(4, 'big', signed=False)

        return res

    @staticmethod
    def FrameType():
        raise NotImplementedException('A subclass of FrameBase should implement FrameType() method')


class SettingFrame(FrameBase):
    """docstring for SettingFrame"""
    def __init__(self, length: int, type_, flags: bytes, stream_identifier: int, data=None):
        super(SettingFrame, self).__init__(length, type_, flags, stream_identifier)
        logger.debug('SettingFrame is called. flag={}, '.format(flags) +\
                     'stream_identifier is {} '.format(stream_identifier) +\
                     'and payload size is {}'.format(length))

        self.params = {b'\x00\x02': self.set_enable_push,
                       b'\x00\x03': self.set_max_concurrent_streams,
                       b'\x00\x04': self.set_initial_window_size,
                       } # TODO: handle other parameters

        payload = BytesIO(data)
        while True:
            identifier = payload.read(2)
            if len(identifier) != 2:
                break

            value = payload.read(4)
            if len(value) != 4:
                break
            self.params[identifier](value)

    def set_enable_push(self, value):
        self.enable_push = int.from_bytes(value, 'big', signed=False)
        logger.debug('enable_push: {}'.format(self.enable_push))

    def set_initial_window_size(self, value):
        self.initial_window_size = int.from_bytes(value, 'big', signed=False)
        logger.debug('initial_window_size: {}'.format(self.initial_window_size))

    def set_max_concurrent_streams(self, value):
        self.max_concurrent_streams = int.from_bytes(value, 'big', signed=False)
        logger.debug('max_concurrent_streams: {}'.format(self.max_concurrent_streams))

    def save(self):
        base = super(SettingFrame, self).save()
        # TODO: enable to alter settings parameters
        return base

    @staticmethod
    def FrameType():
        return FrameTypes.SETTINGS


class WindowUpdate(FrameBase):
    """docstring for WindowUpdate"""
    def __init__(self, length: int, type_, flags: bytes, stream_identifier: int, data=None):
        super(WindowUpdate, self).__init__(length, type_, flags, stream_identifier)
        logger.debug('WindowUpdate is called. flag={}, '.format(flags) +\
                     'stream_identifier is {} '.format(stream_identifier) +\
                     'and payload size is {}'.format(length))

        payload = BytesIO(data)
        self.set_window_size(data)

    def set_window_size(self, value):
        self.window_size = int.from_bytes(value, 'big', signed=False)
        logger.debug('window_size: {}'.format(self.window_size))
        
    def save(self):
        base = super(WindowUpdate, self).save()
        # TODO: enable to alter settings parameters
        return base

    @staticmethod
    def FrameType():
        return FrameTypes.WINDOW_UPDATE

class Headers(FrameBase):

    def __init__(self, length: int, type_, flags: bytes, stream_identifier: int, data=None):
        super(Headers, self).__init__(length, type_, flags, stream_identifier)
        logger.debug('Headers is called. flag={}, '.format(flags) +\
                     'stream_identifier is {} '.format(stream_identifier) +\
                     'and payload size is {}'.format(length))
        int_flags = int.from_bytes(flags, 'big', signed=False)

        self.end_stream = 0x1 & int_flags
        self.end_headers = 0x4 & int_flags
        self.padded = 0x8 & int_flags
        self.priority = 0x20 & int_flags
        logger.debug('{}, {}, {}, {}'.format(self.end_stream,
                                             self.end_headers,
                                             self.padded,
                                             self.priority))

        payload = BytesIO(data)

        if self.padded:
            payload.read(1)

        if self.priority: # TODO: handle priority properly
            self.stream_dependency = payload.read(4)
            self.priority_weight = payload.read(1)
            logger.debug('stream_dependency: {}, '.format(self.stream_dependency) +\
                         'priiority_weight: {}'.format(self.priority_weight))

        self.set_header(payload.read())

    def set_header(self, value):
        decoder = Decoder()
        self.header = decoder.decode(value)
        logger.debug(self.header)

    @staticmethod
    def FrameType():
        return FrameTypes.HEADERS